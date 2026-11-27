"""Gap-filler: PrizePicks CBB lines for games The Odds API has no PrizePicks lines for  ->  data/raw/lines.csv (book "prizepicks", odds_event "pp:<game id>")

    python pipeline/fill_pp_gaps.py [--hours 8] [--dry-run] [--feed-file path.json]

The Odds API's college coverage is patchy: some games have no event at all (Memphis @ Wake Forest, Louisville @ St. John's), and some have sportsbook lines but no PrizePicks ones (Iowa State @ St. John's).
The board only shows PrizePicks lines, so those games vanish. PrizePicks serves its own board as JSON at partner-api.prizepicks.com/projections (no key; undocumented, so it may change or block at any time).
This runs AFTER fetch_lines.py and only touches in-scope ESPN games that start within --hours, are not live, and have NO PrizePicks row from The Odds API in lines.csv. For those it adds the STANDARD lines
(goblin and demon alternates are skipped: they are different bets) for the five markets we use, matched to the ESPN game by team name and start time. Placeholder prices (-137) match the existing PrizePicks rows.
Rows carry odds_event "pp:<PrizePicks game id>", which is how they are told apart; when The Odds API later covers a game, its old "pp:" rows are dropped. Any failure (blocked, changed shape, timeout)
prints a line and exits 0, so the lines workflow carries on exactly as before. Spends no Odds API credits.
"""
import os, sys, csv, argparse, datetime as dt
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import fetch_lines as FL

URL = "https://partner-api.prizepicks.com/projections"
LEAGUE_ID = "20"                                     # CBB (the men's game; WCBB is 176)
STAT = {"Points": "player_points", "Rebounds": "player_rebounds", "Assists": "player_assists", "3-PT Made": "player_threes", "Pts+Rebs+Asts": "player_points_rebounds_assists"}
PRICE = "-137"
RAW, LOG = FL.RAW, FL.LOG


def parse_feed(d):
    """projection dicts: game_id, start (UTC datetime), market, team_name, player, stat (our market key), point, updated"""
    inc = {(i["type"], i["id"]): i["attributes"] for i in d.get("included", [])}
    out = []
    for p in d.get("data", []):
        a, rel = p["attributes"], p["relationships"]
        try:
            if rel["league"]["data"]["id"] != LEAGUE_ID: continue
            if a.get("odds_type") != "standard" or a.get("status") != "pre_game" or a.get("is_live") or a.get("in_game"): continue
            if a.get("projection_type") != "Single Stat" or a.get("stat_type") not in STAT: continue
            pl = inc.get(("new_player", rel["new_player"]["data"]["id"]))
            if not pl or pl.get("combo"): continue
            start = dt.datetime.fromisoformat(a["start_time"]).astimezone(dt.timezone.utc)
            out.append({"game_id": a["game_id"], "start": start, "market": pl.get("market") or "", "team_name": pl.get("team_name") or "", "player": pl["display_name"] if "display_name" in pl else pl["name"],
                        "stat": STAT[a["stat_type"]], "point": float(a["line_score"]), "updated": a.get("updated_at") or a.get("board_time") or ""})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def team_keys(name, aliases):
    k = FL.norm_team(name); return {k, aliases.get(k, k)}


def match(sched_row, projs, aliases):
    """projections for one ESPN game: the player's school (market + team name) is the home or away team and the start is within 3 hours"""
    home, away = team_keys(sched_row["home"], aliases), team_keys(sched_row["away"], aliases)
    t0 = dt.datetime.fromisoformat(sched_row["start_utc"].replace("Z", "+00:00")); hit = []
    for p in projs:
        if abs((p["start"] - t0).total_seconds()) >= 3 * 3600: continue
        full = FL.norm_team(f"{p['market'].replace('Miami (FL)', 'Miami')} {p['team_name']}")   # exact name only: a school-name prefix would join "Texas" to "Texas State"
        if any(full in ks or aliases.get(full, full) in ks for ks in (home, away)): hit.append(p)
    return hit


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--hours", type=float, default=C.LINES_HORIZON_HOURS); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--feed-file"); a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    with open(os.path.join(RAW, "schedule.csv"), newline="") as f: sched = [r for r in csv.DictReader(f) if r["in_scope"] == "1"]
    sched = [r for r in sched if now - dt.timedelta(minutes=5) <= dt.datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00")) <= now + dt.timedelta(hours=a.hours)]
    latest = os.path.join(RAW, "lines.csv"); old = []
    if os.path.exists(latest):
        with open(latest, newline="") as f: old = list(csv.DictReader(f))
    covered = {r["espn_event"] for r in old if r["book"] == "prizepicks" and not r["odds_event"].startswith("pp:")}
    gaps = [r for r in sched if r["event"] not in covered]
    print(f"in-scope games starting within {a.hours:g}h: {len(sched)}; with PrizePicks lines from The Odds API: {len(sched) - len(gaps)}; gaps: {len(gaps)}")
    if not gaps: return
    try:
        if a.feed_file:
            import json; d = json.load(open(a.feed_file))
        else:
            r = requests.get(URL, params={"per_page": 10000}, timeout=45, headers={"User-Agent": "cbb-lines-gapfill/1.0"})
            if not r.ok: print(f"PrizePicks feed: HTTP {r.status_code}, nothing filled"); return
            d = r.json()
        projs = parse_feed(d)
    except Exception as e:
        print(f"PrizePicks feed unavailable ({type(e).__name__}: {e}), nothing filled"); return
    aliases = FL.load_aliases(); pulled_at = now.isoformat(timespec="seconds"); new_rows = []
    print(f"feed: {len(projs)} standard pre-game CBB lines in our five markets")
    for g in gaps:
        hit = match(g, projs, aliases); seen = {}
        for p in sorted(hit, key=lambda p: p["updated"]): seen[(p["stat"], p["player"])] = p                         # one standard line per player and market, the latest
        if not seen: print(f"  {g['away']} @ {g['home']} ({g['start_utc']}): not on the PrizePicks board"); continue
        gid = next(iter(seen.values()))["game_id"]
        for (stat, player), p in seen.items():
            new_rows.append({"pulled_at": pulled_at, "odds_event": "pp:" + gid, "espn_event": g["event"], "commence": g["start_utc"].replace("Z", ":00Z") if len(g["start_utc"]) == 17 else g["start_utc"], "home": g["home"], "away": g["away"],
                             "book": "prizepicks", "market": stat, "player": player, "point": p["point"], "over": PRICE, "under": PRICE, "last_update": p["updated"]})
        print(f"  {g['away']} @ {g['home']} ({g['start_utc']}): {len(seen)} lines filled from PrizePicks")
    if a.dry_run: print("dry run: nothing written"); return
    filled_events = {r["espn_event"] for r in new_rows}
    keep = [r for r in old if not (r["odds_event"].startswith("pp:") and (r["espn_event"] in covered or r["espn_event"] in {g["event"] for g in gaps}))]   # refresh our own rows for these games, and drop ones The Odds API now covers
    prev = {(r["espn_event"], r["market"], r["player"], r["point"]) for r in old if r["odds_event"].startswith("pp:")}
    changed = [r for r in new_rows if (r["espn_event"], r["market"], r["player"], str(r["point"])) not in prev]
    with open(latest, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FL.COLS); w.writeheader(); w.writerows(keep + new_rows)
    if changed:
        FL.append(os.path.join(LOG, "lines_log.csv"), FL.COLS, [[r[c] for c in FL.COLS] for r in changed])
    print(f"fill: {len(new_rows)} PrizePicks lines in {len(filled_events)} games, {len(changed)} new or moved; no Odds API credits used")


if __name__ == "__main__":
    main()
