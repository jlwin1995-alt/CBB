"""Did The Odds API ever list (and price) games our live pulls missed?  A tiny, budgeted look at the HISTORICAL endpoints (nothing here feeds the model, the site or lines.csv).

    ODDS_API_KEY=... python pipeline/probe_historical.py --date 2026-11-27T01:30:00Z [--teams "St. John's,Kansas State,Omaha"] [--market player_points] [--max-games 3]

Step 1: /historical/sports/{sport}/events?date=... (about 1 credit) lists the events the API knew at that moment; those involving any --teams name are printed.
Step 2: for each such event (up to --max-games) one /historical/.../events/{id}/odds call for ONE market at the same snapshot (about 10 credits each) says whether any book, PrizePicks included, had lines.
Spend is written to data/log/credits.csv ("HISTORICAL ..." rows) so the daily cap stays honest; the results only go to the run log and the run summary. A plan without historical access shows as an HTTP 401/403/422 line.
"""
import os, sys, csv, argparse, datetime as dt
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import fetch_lines as FL

LOG = FL.LOG


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--date", required=True); ap.add_argument("--teams", default="St. John's,Kansas State,Omaha")
    ap.add_argument("--market", default="player_points"); ap.add_argument("--max-games", type=int, default=3); a = ap.parse_args()
    key = os.environ.get("ODDS_API_KEY")
    if not key: sys.exit("no ODDS_API_KEY")
    teams = [FL.norm_team(t) for t in a.teams.split(",") if t.strip()]
    s = requests.Session(); out = []
    r = s.get(f"{FL.BASE}/historical/sports/{C.SPORT}/events", params={"apiKey": key, "date": a.date, "dateFormat": "iso"}, timeout=40)
    if not r.ok: sys.exit(f"historical events: HTTP {r.status_code} {r.text[:200]}")
    used = float(r.headers.get("x-requests-last", 0) or 0); left = float(r.headers.get("x-requests-remaining", "nan")); total = used
    j = r.json(); events = j.get("data", []); print(f"snapshot {j.get('timestamp')}: {len(events)} NCAAB events listed; {used:g} credits, {left:g} left")
    hit = [e for e in events if any(t in FL.norm_team(e["home_team"]) or t in FL.norm_team(e["away_team"]) for t in teams)]
    for e in events:
        if e in hit: print(f"  MATCH {e['away_team']} @ {e['home_team']} {e['commence_time']} id {e['id']}")
    out.append(f"{len(events)} events at {j.get('timestamp')}; {len(hit)} involve {a.teams}")
    cred = os.path.join(LOG, "credits.csv"); now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"); et = dt.datetime.now(FL.ET).date().isoformat()
    rows = [[now, et, "", "HISTORICAL events " + a.date, used, left]]
    for e in hit[:a.max_games]:
        if total + 10 > 40 or (left == left and left - 10 < C.CREDIT_FLOOR): print("budget stop"); break
        rr = s.get(f"{FL.BASE}/historical/sports/{C.SPORT}/events/{e['id']}/odds", timeout=40, params={"apiKey": key, "date": a.date, "bookmakers": ",".join(C.ODDS_BOOKS), "markets": a.market, "oddsFormat": "american", "dateFormat": "iso"})
        game = f"{e['away_team']} @ {e['home_team']}"
        if not rr.ok: print(f"  {game}: HTTP {rr.status_code} {rr.text[:160]}"); out.append(f"{game}: HTTP {rr.status_code}"); continue
        u = float(rr.headers.get("x-requests-last", 0) or 0); left = float(rr.headers.get("x-requests-remaining", "nan")); total += u
        books = {b["key"]: sum(len(m["outcomes"]) for m in b["markets"]) for b in rr.json().get("data", {}).get("bookmakers", [])}
        print(f"  {game}: {u:g} credits, outcomes by book {books or 'none'}"); out.append(f"{game}: {books or 'no lines'} ({u:g} credits)")
        rows.append([now, et, e["id"], "HISTORICAL " + game, u, left])
    FL.append(cred, ["ts", "et_date", "odds_event", "game", "used", "left"], rows)
    print(f"done: {total:g} credits, {left:g} left")
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        with open(sp, "a") as f: f.write("### Historical probe\n\n" + "\n".join(f"- {x}" for x in out) + f"\n\n{total:g} credits used, {left:g} left\n")


if __name__ == "__main__":
    main()
