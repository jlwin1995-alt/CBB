"""Which extra player-prop markets does The Odds API actually return for college games?  A small, budgeted probe (nothing here feeds the model or the site).

    ODDS_API_KEY=... python pipeline/probe_markets.py [--games 4] [--hours 14] [--markets a,b,c] [--dry-run]

Default markets are the four combo props the NBA project uses (points + rebounds + assists, points + rebounds, points + assists, rebounds + assists). The Odds API lists them for NCAAB, but listing a key
is not the same as sportsbooks and PrizePicks posting lines on it for college games. The probe asks the same /events/{id}/odds endpoint, with the same book list, for a few in-scope games starting within --hours,
choosing the games that already have base-market props in data/raw/lines.csv (props are most likely there) plus one with few, and reports for each market: which books returned it, how many players and lines,
and whether PrizePicks is among them. Cost: 1 credit per market per game that returns data (0 for a market with no data), so --games 4 with four markets is at most 16. The spend is written to
data/log/credits.csv like any pull (so the daily cap stays honest) and the results to data/log/market_probe.json. lines.csv and lines_log.csv are NOT touched.
"""
import os, sys, csv, json, time, argparse, datetime as dt
from zoneinfo import ZoneInfo
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import fetch_lines as FL

ROOT = FL.ROOT
RAW, LOG = FL.RAW, FL.LOG
COMBOS = ["player_points_rebounds_assists", "player_points_rebounds", "player_points_assists", "player_rebounds_assists"]
ET = ZoneInfo("America/New_York")


def pick_games(sched, base_lines):
    """prefer games that already have base-market props; add one with few lines to see the long tail"""
    cnt = {}
    for r in base_lines: cnt[r["espn_event"]] = cnt.get(r["espn_event"], 0) + 1
    ranked = sorted(sched, key=lambda r: -cnt.get(r["event"], 0))
    return ranked, cnt


def summarize(j, markets):
    out = {m: {"books": {}, "players": set(), "lines": 0} for m in markets}
    for b in j.get("bookmakers", []):
        for m in b.get("markets", []):
            if m["key"] not in out: continue
            o = out[m["key"]]
            n = len({(x.get("description"), x.get("point")) for x in m.get("outcomes", [])})
            o["books"][b["key"]] = n; o["lines"] += n
            o["players"].update(x.get("description") for x in m.get("outcomes", []))
    return {m: {"books": o["books"], "players": len(o["players"]), "lines": o["lines"], "prizepicks": "prizepicks" in o["books"]} for m, o in out.items()}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--games", type=int, default=4); ap.add_argument("--hours", type=float, default=14.0)
    ap.add_argument("--markets", default=",".join(COMBOS)); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
    markets = [m.strip() for m in a.markets.split(",") if m.strip()]
    key = os.environ.get("ODDS_API_KEY")
    now = dt.datetime.now(dt.timezone.utc)
    with open(os.path.join(RAW, "schedule.csv"), newline="") as f: sched = [r for r in csv.DictReader(f) if r["in_scope"] == "1"]
    sched = [r for r in sched if now - dt.timedelta(minutes=5) <= dt.datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00")) <= now + dt.timedelta(hours=a.hours)]
    lp = os.path.join(RAW, "lines.csv")
    base = list(csv.DictReader(open(lp, newline=""))) if os.path.exists(lp) else []
    ranked, cnt = pick_games(sched, base)
    if a.games <= 1 or len(ranked) <= a.games: chosen = ranked[:a.games]
    else: chosen = ranked[:a.games - 1] + [ranked[-1]]          # the games with the most props, plus the one with the fewest (the long tail)
    print(f"in-scope games starting within {a.hours:g}h: {len(sched)}; probing {len(chosen)} for {len(markets)} markets ({', '.join(markets)})")
    for r in chosen: print(f"  {r['away']} @ {r['home']} ({r['start_utc']}): {cnt.get(r['event'], 0)} base-market lines already known")
    if a.dry_run or not key:
        print("dry run" if a.dry_run else "no ODDS_API_KEY: nothing pulled"); return
    s = requests.Session()
    r = s.get(f"{FL.BASE}/sports/{C.SPORT}/events", params={"apiKey": key, "dateFormat": "iso"}, timeout=30); r.raise_for_status()
    left = float(r.headers.get("x-requests-remaining", "nan"))
    matched, _ = FL.match_events(r.json(), chosen, FL.load_aliases())
    credlog = os.path.join(LOG, "credits.csv"); pulled_at = now.isoformat(timespec="seconds"); results = []; used_total = 0.0
    for e, row in matched:
        spent = FL.credits_today(credlog); est = len(markets)
        if spent + est > C.DAILY_CREDIT_CAP: print(f"daily cap {C.DAILY_CREDIT_CAP} would be passed ({spent:g} spent): stopping"); break
        if left == left and left - est < C.CREDIT_FLOOR: print(f"credit floor {C.CREDIT_FLOOR} reached ({left:g} left): stopping"); break
        rr = s.get(f"{FL.BASE}/sports/{C.SPORT}/events/{e['id']}/odds", timeout=40, params={"apiKey": key, "bookmakers": ",".join(C.ODDS_BOOKS), "markets": ",".join(markets), "oddsFormat": "american", "dateFormat": "iso"})
        if rr.status_code in (401, 429): sys.exit(f"Odds API {rr.status_code}: {rr.text[:200]}")
        game = f"{e['away_team']} @ {e['home_team']}"
        if not rr.ok: print(f"  {game}: HTTP {rr.status_code} {rr.text[:160]}"); results.append({"game": game, "error": f"HTTP {rr.status_code} {rr.text[:160]}"}); continue
        used = float(rr.headers.get("x-requests-last", 0) or 0); left = float(rr.headers.get("x-requests-remaining", "nan")); used_total += used
        FL.append(credlog, ["ts", "et_date", "odds_event", "game", "used", "left"], [[pulled_at, dt.datetime.now(ET).date().isoformat(), e["id"], "PROBE " + game, used, left]])
        sm = summarize(rr.json(), markets)
        results.append({"game": game, "start_utc": row["start_utc"], "tier": f"{row.get('home_tier')}/{row.get('away_tier')}", "base_lines_known": cnt.get(row["event"], 0), "credits": used, "markets": sm})
        print(f"  {game} ({row.get('home_tier')}/{row.get('away_tier')}, {used:g} credits)")
        for m, v in sm.items(): print(f"    {m}: {v['lines']} lines, {v['players']} players, books {sorted(v['books']) or 'none'}{' (PrizePicks yes)' if v['prizepicks'] else ''}")
        time.sleep(0.3)
    # roll-up per market across the probed games
    roll = {m: {"games_with_data": 0, "games": len(results), "books": set(), "lines": 0, "prizepicks_games": 0} for m in markets}
    for g in results:
        for m, v in g.get("markets", {}).items():
            if v["lines"]: roll[m]["games_with_data"] += 1
            roll[m]["books"].update(v["books"]); roll[m]["lines"] += v["lines"]; roll[m]["prizepicks_games"] += int(v["prizepicks"])
    summary = {m: {**{k: (sorted(x) if isinstance(x, set) else x) for k, x in v.items()}} for m, v in roll.items()}
    print(f"\nprobe done: {len(results)} games, {used_total:g} credits used, {left:g} left")
    for m, v in summary.items(): print(f"  {m}: data in {v['games_with_data']} of {v['games']} games, {v['lines']} lines, PrizePicks in {v['prizepicks_games']}, books {v['books']}")
    os.makedirs(LOG, exist_ok=True)
    jp = os.path.join(LOG, "market_probe.json"); hist = json.load(open(jp)) if os.path.exists(jp) else []
    hist.append({"ts": pulled_at, "markets": markets, "credits": used_total, "summary": summary, "games": results}); json.dump(hist, open(jp, "w"), indent=1)
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        with open(sp, "a") as f:
            f.write(f"### Combo-market probe ({len(results)} games, {used_total:g} credits)\n\n| market | games with data | lines | PrizePicks games | books |\n|---|---|---|---|---|\n")
            for m, v in summary.items(): f.write(f"| {m} | {v['games_with_data']} of {v['games']} | {v['lines']} | {v['prizepicks_games']} | {', '.join(v['books']) or 'none'} |\n")


if __name__ == "__main__":
    main()
