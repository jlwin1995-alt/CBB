"""Daily ESPN ingest for the current season  ->  data/raw/players_<season>.csv.gz, games_<season>.csv, schedule.csv

    python pipeline/ingest_daily.py [--season 2027] [--days-back 2]

Box scores for every finished Division I game since the last ingested date (minus a small overlap, events already stored are skipped), appended in the same
layout as the backfill, then the schedule for the next two Eastern dates (scheduled or in-progress games) with both teams' tiers and an in_scope flag
(at least one power-6 or mid-major team; the user's scope, Nov 3 2026). Safe to run twice.
"""
import os, sys, csv, gzip, json, argparse, datetime as dt
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backfill_espn as bf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "raw")
ET = ZoneInfo("America/New_York")


def current_season(today):
    return today.year + 1 if today.month >= 8 else today.year


def stored_events(gf):
    if not os.path.exists(gf): return set(), None
    ev, last = set(), None
    with open(gf, newline="") as f:
        for r in csv.DictReader(f):
            ev.add(r["event"]); last = max(last or r["date"], r["date"])
    return ev, last


def ingest_days(season, d0, d1):
    pf, gf = f"{DATA}/players_{season}.csv.gz", f"{DATA}/games_{season}.csv"
    if not os.path.exists(pf):
        with gzip.open(pf, "wt", newline="") as f: csv.writer(f).writerow(bf.PH)
        with open(gf, "w", newline="") as f: csv.writer(f).writerow(bf.GH)
    have, _ = stored_events(gf); added = failed = 0; day = d0
    while day <= d1:
        sb = bf.get(bf.B + "/scoreboard", {"dates": day.strftime("%Y%m%d"), "groups": "50", "limit": "400"})
        if sb is None: print("scoreboard failed", day, flush=True); day += dt.timedelta(days=1); continue
        evs = [e for e in sb.get("events", []) if e["status"]["type"]["name"] == "STATUS_FINAL" and e["id"] not in have]
        with ThreadPoolExecutor(12) as ex: res = list(ex.map(bf.one, evs))
        with gzip.open(pf, "at", newline="") as f, open(gf, "a", newline="") as g:
            w, gw = csv.writer(f), csv.writer(g)
            for ev, (eid, rows, teams) in zip(evs, res):
                if not rows: failed += 1; continue
                c = ev["competitions"][0]; cp = {x["homeAway"]: x for x in c["competitors"]}
                if "home" not in cp or "away" not in cp: failed += 1; continue
                w.writerows(rows); added += 1; have.add(eid)
                gw.writerow([eid, ev["date"][:10], season, cp["home"]["team"]["id"], cp["home"]["team"].get("displayName"), cp["home"].get("score"),
                             cp["away"]["team"]["id"], cp["away"]["team"].get("displayName"), cp["away"].get("score"), int(bool(c.get("neutralSite"))), int(bool(c.get("conferenceCompetition")))])
        print(day, "finished games found", len(evs), flush=True); day += dt.timedelta(days=1)
    return added, failed


def schedule(today_et):
    tiers = {}
    with open(f"{DATA}/team_tiers.csv", newline="") as f:
        for r in csv.DictReader(f): tiers[r["team_id"]] = (r["tier"], r["conference"])
    rows = []
    for k in range(0, 2):
        d = today_et + dt.timedelta(days=k)
        sb = bf.get(bf.B + "/scoreboard", {"dates": d.strftime("%Y%m%d"), "groups": "50", "limit": "400"}) or {}
        for e in sb.get("events", []):
            if e["status"]["type"]["name"] == "STATUS_FINAL": continue
            c = e["competitions"][0]; cp = {x["homeAway"]: x for x in c["competitors"]}
            if "home" not in cp or "away" not in cp: continue
            h, a = cp["home"]["team"], cp["away"]["team"]; th, ta = tiers.get(str(h["id"]), ("low", "")), tiers.get(str(a["id"]), ("low", ""))
            scope = int(th[0] in ("power6", "mid") or ta[0] in ("power6", "mid"))
            rows.append([e["id"], e["date"], d.isoformat(), h["id"], h.get("displayName"), th[0], th[1], a["id"], a.get("displayName"), ta[0], ta[1], int(bool(c.get("neutralSite"))), scope, e["status"]["type"]["name"]])
    with open(f"{DATA}/schedule.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["event", "start_utc", "et_date", "home_id", "home", "home_tier", "home_conf", "away_id", "away", "away_tier", "away_conf", "neutral", "in_scope", "status"]); w.writerows(sorted(rows, key=lambda r: r[1]))
    return rows


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--season", type=int); ap.add_argument("--days-back", type=int, default=2); a = ap.parse_args()
    now = dt.datetime.now(ET); today = now.date(); season = a.season or current_season(today)
    _, last = stored_events(f"{DATA}/games_{season}.csv")
    d0 = (dt.date.fromisoformat(last) - dt.timedelta(days=a.days_back)) if last else dt.date(season - 1, 11, 1)
    d0 = max(d0, dt.date(season - 1, 11, 1))
    added, failed = ingest_days(season, d0, today)
    rows = schedule(today)
    print(f"season {season}: games added {added}, failed {failed}; schedule {len(rows)} games ({sum(r[12] for r in rows)} in scope)")


if __name__ == "__main__":
    main()
