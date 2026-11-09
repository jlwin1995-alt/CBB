"""data/ -> site/data/board.json and site/data/scorecard.json (the two pages of the CBB site).

    python pipeline/build_site.py

Board: PrizePicks lines for games with no box score yet, each with the sportsbook CONSENSUS (median closing point of the other books, and how many books), the model
projection from the pre-tip log and the edge (projection minus the PrizePicks line). Scorecard: the running tally from grade_lines.py, the model's hit rate, and the
latest graded lines. Only PrizePicks lines are shown (user, Nov 8, 2026); the other books appear only through the consensus.
"""
import os, sys, json, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grade_lines as GL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, LOG, PROJ, OUT = os.path.join(ROOT, "data", "raw"), os.path.join(ROOT, "data", "log"), os.path.join(ROOT, "data", "proj"), os.path.join(ROOT, "site", "data")
MARKET_LABEL = {"player_points": "Points", "player_rebounds": "Rebounds", "player_assists": "Assists", "player_threes": "3-pointers"}
BACKTEST = [   # research/validate_model.py, roster = who played; FP = PrizePicks fantasy score (points 1, rebounds 1.2, assists 1.5, steals/blocks 3, turnovers -1)
    {"window": "2026 Dec-Mar", "fp_model": 6.75, "fp_avg": 6.70, "min_model": 5.09, "min_avg": 5.18},
    {"window": "2025 Dec-Mar (holdout)", "fp_model": 6.56, "fp_avg": 6.53, "min_model": 5.06, "min_avg": 5.15},
    {"window": "2026 Nov 5-30", "fp_model": 7.13, "fp_avg": 7.33, "min_model": 5.67, "min_avg": 5.13},
    {"window": "2025 Nov 5-30", "fp_model": 7.05, "fp_avg": 7.31, "min_model": 5.62, "min_avg": 5.14},
]
KEY = ["espn_event", "book", "market", "player"]


def num(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else (round(float(x), 2) if isinstance(x, (float, np.floating)) else x)


def board(now):
    lp = os.path.join(RAW, "lines.csv")
    if not os.path.exists(lp): return {"games": []}
    lines = pd.read_csv(lp, dtype={"espn_event": str}).sort_values("pulled_at").drop_duplicates(KEY, keep="last")
    gp = os.path.join(LOG, "lines_graded.csv")
    done = set(pd.read_csv(gp, dtype={"espn_event": str}).espn_event) if os.path.exists(gp) else set()
    box = GL.load_boxes(); done |= set(box["event"])
    lines = lines[~lines.espn_event.isin(done)]
    sb = lines[lines.book != "prizepicks"]
    if len(sb):                                   # no sportsbook lines at all (the usual case) must not crash the build
        cons = sb.groupby(["espn_event", "market", "player"]).point.agg(consensus="median", n_books="count").reset_index()
        books = (sb.assign(s=sb.book + " " + sb.point.map(lambda p: f"{p:g}")).groupby(["espn_event", "market", "player"]).s
                 .agg(", ".join).rename("book_lines").reset_index())
    else:
        cons = pd.DataFrame(columns=["espn_event", "market", "player", "consensus", "n_books"])
        books = pd.DataFrame(columns=["espn_event", "market", "player", "book_lines"])
    pp = lines[lines.book == "prizepicks"].merge(cons, on=["espn_event", "market", "player"], how="left").merge(books, on=["espn_event", "market", "player"], how="left")
    pl = os.path.join(LOG, "proj_log.csv")
    proj = pd.read_csv(pl, dtype={"event": str, "pid": str, "team_id": str}).dropna(subset=["pts_p"]).drop_duplicates(["event", "pid"], keep="last") if os.path.exists(pl) else pd.DataFrame()
    pidx = {}
    for r in proj.itertuples(index=False): pidx[(r.event, GL.nz(r.name))] = r
    sched = pd.read_csv(os.path.join(RAW, "schedule.csv"), dtype={"event": str}) if os.path.exists(os.path.join(RAW, "schedule.csv")) else pd.DataFrame(columns=["event"])
    sm = sched.drop_duplicates("event").set_index("event")
    games = {}
    for r in pp.itertuples(index=False):
        t0 = pd.Timestamp(r.commence)
        if t0 < now - pd.Timedelta(hours=4): continue
        g = games.setdefault(r.espn_event, {"event": r.espn_event, "start_utc": r.commence, "home": r.home, "away": r.away, "spread_home": None, "total": None, "lines": []})
        pr = pidx.get((r.espn_event, GL.nz(r.player)))
        st = GL.MARKET_STAT[r.market]
        pv = float(getattr(pr, st + "_p")) if pr is not None else None
        if pr is not None:
            g["spread_home"] = num(pr.spread_home); g["total"] = num(pr.total)
        team = None
        if pr is not None: team = g["home"] if int(pr.is_home) == 1 else g["away"]
        cs = None if r.consensus != r.consensus else float(r.consensus)
        g["lines"].append({"player": r.player, "team": team, "market": MARKET_LABEL.get(r.market, r.market), "pp": float(r.point), "cons": cs, "n_books": int(r.n_books) if r.n_books == r.n_books else 0,
                           "book_lines": r.book_lines if isinstance(r.book_lines, str) else "", "gap": num(float(r.point) - cs) if cs is not None else None,
                           "proj": num(pv), "edge": num(pv - float(r.point)) if pv is not None else None, "min": num(pr.min_p) if pr is not None else None,
                           "new": bool(pr.newcomer) if pr is not None else None, "pulled": r.pulled_at})
    out = sorted(games.values(), key=lambda g: g["start_utc"])
    for g in out: g["lines"].sort(key=lambda l: (l["team"] or "", l["player"], l["market"]))
    return {"asof": now.isoformat(timespec="seconds"), "games": out}


def scorecard(now):
    tp = os.path.join(LOG, "lines_tally.json")
    t = json.load(open(tp)) if os.path.exists(tp) else {}
    gp = os.path.join(LOG, "lines_graded.csv"); recent = []
    if os.path.exists(gp):
        g = pd.read_csv(gp, dtype={"espn_event": str})
        g = g[g.result.isin(["over", "under", "push", "void", "nomatch"])].sort_values(["et_date", "espn_event", "player"], ascending=[False, True, True]).head(150)
        for r in g.itertuples(index=False):
            recent.append({"date": r.et_date, "game": f"{r.away} @ {r.home}", "player": r.player, "market": MARKET_LABEL.get(r.market, r.market), "pp": num(r.point), "cons": num(r.consensus),
                           "proj": num(r.proj), "actual": num(r.actual), "result": r.result, "pick": r.pick if isinstance(r.pick, str) else None})
    return {"asof": now.isoformat(timespec="seconds"), "tally": t, "recent": recent, "backtest": BACKTEST, "breakeven": 0.544}


def main():
    now = pd.Timestamp(dt.datetime.now(dt.timezone.utc))
    os.makedirs(OUT, exist_ok=True)
    b = board(now); s = scorecard(now)
    json.dump(b, open(os.path.join(OUT, "board.json"), "w"), separators=(",", ":"), allow_nan=False)
    json.dump(s, open(os.path.join(OUT, "scorecard.json"), "w"), separators=(",", ":"), allow_nan=False)
    n = sum(len(g["lines"]) for g in b["games"])
    print(f"site data: board {len(b['games'])} games / {n} PrizePicks lines; scorecard {len(s['recent'])} recent graded lines")


if __name__ == "__main__":
    main()
