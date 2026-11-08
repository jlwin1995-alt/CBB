"""Grade every pulled player-prop line against the ESPN box scores  ->  data/log/lines_graded.csv and data/log/lines_tally.json

    python pipeline/grade_lines.py

Reads data/raw/lines.csv (many snapshots per line when the number moved) and keeps the LAST pull of each (game, book, market, player): the closing line. A line is graded
once its game has a box score in data/raw/players_<season>.csv.gz. Result is over / under / push (stat equals the line) / void (player on the sheet with 0 minutes) /
nomatch (game is final but the name was not found; check the aliases). Rebuilt from scratch on every run, so it is safe to run twice.

This grades the LINES, not a model: there is no CBB projection yet. Each row also carries avg_prior, the player's average of the stat over his earlier games (this season
if he has 2+ games, otherwise all stored seasons; blank under 3 games), so a model-free benchmark is available when the tally is read.
"""
import os, re, json, glob, unicodedata
from zoneinfo import ZoneInfo
import pandas as pd, numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, LOG = os.path.join(ROOT, "data", "raw"), os.path.join(ROOT, "data", "log")
ET = ZoneInfo("America/New_York")
MARKET_STAT = {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast", "player_threes": "fg3m"}   # same as config.MARKET_STAT
KEY = ["espn_event", "book", "market", "player"]
OUT_COLS = ["et_date", "espn_event", "home", "away", "book", "market", "player", "point", "over", "under", "pulled_at", "actual", "mins", "result", "avg_prior", "n_prior"]


def nz(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return " ".join(re.sub(r"[^a-z ]", " ", s).split())


def load_boxes():
    frames = []
    for f in sorted(glob.glob(os.path.join(RAW, "players_*.csv.gz"))):
        season = int(re.search(r"players_(\d+)", f).group(1))
        frames.append(pd.read_csv(f, dtype={"pid": str, "event": str}).assign(season=season))
    p = pd.concat(frames, ignore_index=True)
    p["nn"] = p["name"].map(nz)
    p["d"] = pd.to_datetime(p["date"])
    return p


def tally(df):
    out = {}
    for r in ("over", "under", "push", "void", "nomatch"):
        out[r] = int((df["result"] == r).sum())
    dec = out["over"] + out["under"]
    out["decided"] = dec
    out["over_rate"] = round(out["over"] / dec, 3) if dec else None
    out["mean_actual_minus_line"] = round(float((df.loc[df.result.isin(["over", "under"]), "actual"] - df.loc[df.result.isin(["over", "under"]), "point"]).mean()), 2) if dec else None
    return out


def main():
    lp = os.path.join(RAW, "lines.csv")
    if not os.path.exists(lp):
        print("no lines.csv yet"); return
    lines = pd.read_csv(lp, dtype={"espn_event": str})
    lines = lines.sort_values("pulled_at").drop_duplicates(KEY, keep="last")
    box = load_boxes()
    final = set(box["event"])
    by_event = {e: d for e, d in box.groupby("event")}
    rows, unmatched = [], []
    for _, r in lines.iterrows():
        if r.espn_event not in final or r.market not in MARKET_STAT:
            continue
        d = by_event[r.espn_event]
        nn = nz(r.player)
        b = d[d.nn == nn]
        if len(b) == 0:                                   # unique last-name match inside the game
            ln = nn.split()[-1] if nn else ""
            cand = d[d.nn.str.split().str[-1] == ln]
            b = cand if len(cand) == 1 else b
        et = pd.Timestamp(r.commence).tz_convert(ET).strftime("%Y-%m-%d") if pd.notna(r.commence) else ""
        base = dict(et_date=et, espn_event=r.espn_event, home=r.home, away=r.away, book=r.book, market=r.market, player=r.player, point=r.point,
                    over=r.over, under=r.under, pulled_at=r.pulled_at)
        if len(b) == 0:
            unmatched.append((r.player, r.home, r.away))
            rows.append(dict(base, actual=np.nan, mins=np.nan, result="nomatch", avg_prior=np.nan, n_prior=0)); continue
        b = b.iloc[0]; st = MARKET_STAT[r.market]
        actual = b[st]
        res = "void" if b["min"] <= 0 else ("push" if actual == r.point else ("over" if actual > r.point else "under"))
        hist = box[(box.pid == b.pid) & (box.d < b.d) & (box["min"] > 0)]
        cur = hist[hist.season == b.season]
        use = cur if len(cur) >= 2 else hist
        avg = float(use[st].mean()) if len(use) >= 3 else np.nan
        rows.append(dict(base, actual=actual, mins=b["min"], result=res, avg_prior=round(avg, 2) if avg == avg else np.nan, n_prior=len(use)))
    g = pd.DataFrame(rows, columns=OUT_COLS)
    g = g.sort_values(["et_date", "espn_event", "player", "market", "book"]) if len(g) else g
    os.makedirs(LOG, exist_ok=True)
    g.to_csv(os.path.join(LOG, "lines_graded.csv"), index=False)
    pending = int(len(lines) - len(g))
    t = {"through": str(g["et_date"].max()) if len(g) else None, "graded_rows": int(len(g)), "pending_rows": pending,
         "total": tally(g) if len(g) else {}, "by_market": {}, "by_book": {}, "by_date": {}}
    for k, col in (("by_market", "market"), ("by_book", "book"), ("by_date", "et_date")):
        for v, d in g.groupby(col):
            t[k][str(v)] = tally(d)
    pp = g[g.book == "prizepicks"]
    t["prizepicks"] = tally(pp) if len(pp) else {}
    with open(os.path.join(LOG, "lines_tally.json"), "w") as f:
        json.dump(t, f, indent=1)
    print(f"graded {len(g)} closing lines ({pending} still waiting on box scores); total {t['total']}")
    if unmatched:
        print(f"::warning::{len(unmatched)} lines in finished games had no matching box-score name: {unmatched[:10]}")


if __name__ == "__main__":
    main()
