"""Project every player in the upcoming in-scope games  ->  data/proj/projections.csv (current snapshot) and data/log/proj_log.csv (frozen at tip)

    python pipeline/project.py [--hours 36]

Games come from data/raw/schedule.csv (written by ingest_daily.py): in-scope games that have not started, starting within --hours. Rosters are ESPN's current team
rosters (free), so transfers and freshmen are on the right team; the model (pipeline/model.py) projects minutes and per-game stats for each rostered player.
The DraftKings spread and total from ESPN's game page (free) are stored beside each projection but are NOT model inputs yet.

proj_log.csv is what lines are graded against: rows for a game are replaced on every run until the game starts, then never touched again, so the logged
projection is the last one made before tip. Availability is not modelled (no injury feed): a player with no line is simply not graded.
"""
import os, sys, argparse, datetime as dt
import requests, pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as M, recruits as RC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, LOG, PROJ = os.path.join(ROOT, "data", "raw"), os.path.join(ROOT, "data", "log"), os.path.join(ROOT, "data", "proj")
API = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
LOG_COLS = ["logged_at", "event", "et_date", "start_utc", "home", "away", "team_id", "opp_id", "is_home", "pid", "name", "pos", "newcomer", "bucket", "n_games", "note",
            "min_p", "pts_p", "reb_p", "ast_p", "fg3m_p", "stl_p", "blk_p", "tov_p", "spread_home", "total"]
MIN_KEEP = 4.0          # roster players projected under this many minutes are left out of the files


def get(url, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200: return r.json()
        except requests.RequestException:
            pass
    return None


def roster(team_id):
    d = get(f"{API}/teams/{team_id}/roster")
    out = []
    for a in (d or {}).get("athletes", []):
        out.append((str(a["id"]), a.get("fullName") or a.get("displayName"), (a.get("position") or {}).get("abbreviation", "G")))
    return out


def lines_for(event):
    d = get(f"{API}/summary?event={event}")
    pc = (d or {}).get("pickcenter") or []
    if not pc: return np.nan, np.nan
    p = pc[0]
    return p.get("spread", np.nan), p.get("overUnder", np.nan)


def load_history(season):
    bx, gm = [], []
    for y in (season - 2, season - 1, season):
        pf, gf = f"{RAW}/players_{y}.csv.gz", f"{RAW}/games_{y}.csv"
        if os.path.exists(pf) and os.path.exists(gf):
            bx.append(pd.read_csv(pf, dtype={"pid": str, "team_id": str, "event": str}).assign(season=y))
            gm.append(pd.read_csv(gf, dtype={"home_id": str, "away_id": str, "event": str}).assign(season=y))
    return M.prep(pd.concat(bx, ignore_index=True), pd.concat(gm, ignore_index=True))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--hours", type=float, default=36); A = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    s = pd.read_csv(f"{RAW}/schedule.csv", dtype={"event": str, "home_id": str, "away_id": str})
    s["start"] = pd.to_datetime(s["start_utc"], utc=True)
    s = s[(s.in_scope == 1) & (s.start > now) & (s.start <= now + dt.timedelta(hours=A.hours)) & (s.status == "STATUS_SCHEDULED")]
    if s.empty:
        print("no upcoming in-scope games"); return
    season = int(pd.read_csv(f"{RAW}/games_{max(int(f.split('_')[1].split('.')[0]) for f in os.listdir(RAW) if f.startswith('games_'))}.csv").season.max())
    P, G = load_history(season)
    asof = pd.Timestamp(now.date()) + pd.Timedelta(days=1)          # all box scores stored so far
    try:
        tab, _, cur = RC.learn(season)
    except Exception as e:                                          # no recruit file for this class yet: project without the rank prior
        print("::warning::recruit prior unavailable:", e); tab, cur = None, None
    rows = []
    for g in s.itertuples():
        for tid, oid, home in ((g.home_id, g.away_id, 1), (g.away_id, g.home_id, 0)):
            for pid, name, pos in roster(tid):
                rows.append(dict(event=g.event, team_id=tid, opp_id=oid, is_home=home, pid=pid, name=name, pos=pos))
    slate = pd.DataFrame(rows)
    if slate.empty:
        print("no rosters returned"); return
    pr = M.project(P, G, slate[["event", "team_id", "opp_id", "is_home", "pid", "pos"]], season, asof, tab, cur)
    pr = pr.merge(slate[["event", "pid", "name", "pos", "is_home"]], on=["event", "pid"], how="left")
    meta = s.set_index("event")
    pr["et_date"] = pr.event.map(meta.et_date); pr["start_utc"] = pr.event.map(meta.start_utc); pr["home"] = pr.event.map(meta.home); pr["away"] = pr.event.map(meta.away)
    ctx = {e: lines_for(e) for e in s.event}
    pr["spread_home"] = pr.event.map(lambda e: ctx[e][0]); pr["total"] = pr.event.map(lambda e: ctx[e][1])
    pr["logged_at"] = now.isoformat(timespec="seconds")
    n_skipped = int(pr.min_p.isna().sum())
    pr = pr[pr.min_p >= MIN_KEEP]
    pr = pr[LOG_COLS].round(3).sort_values(["start_utc", "event", "team_id", "min_p"], ascending=[True, True, True, False])
    os.makedirs(PROJ, exist_ok=True); os.makedirs(LOG, exist_ok=True)
    pr.to_csv(f"{PROJ}/projections.csv", index=False)
    lp = f"{LOG}/proj_log.csv"
    old = pd.read_csv(lp, dtype={"event": str, "pid": str, "team_id": str, "opp_id": str}) if os.path.exists(lp) else pd.DataFrame(columns=LOG_COLS)
    if len(old):
        started = pd.to_datetime(old.start_utc, utc=True) <= now
        keep = old[started | ~old.event.isin(set(pr.event))]          # a game that has started is frozen; others are replaced by this run
    else:
        keep = old
    out = pd.concat([keep, pr], ignore_index=True)
    out.to_csv(lp, index=False)
    proj = pr.dropna(subset=["pts_p"])
    print(f"projected {len(proj)} players in {pr.event.nunique()} games ({n_skipped} unranked newcomers with under 3 games left out); log now {len(out)} rows, {out.event.nunique()} games; "
          f"spread/total found for {sum(1 for v in ctx.values() if v[0] == v[0])} of {len(ctx)} games")


if __name__ == "__main__":
    main()
