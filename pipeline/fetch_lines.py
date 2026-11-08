"""College-basketball player-prop lines from The Odds API  ->  data/raw/lines.csv (latest per line) and data/log/lines_log.csv (every changed snapshot)

    ODDS_API_KEY=... python pipeline/fetch_lines.py [--hours 8] [--dry-run]

Games come from data/raw/schedule.csv (written by ingest_daily.py): only in-scope games (a power-6 or mid-major team) starting within --hours. The free /events listing
gives the Odds API's game ids, which are matched to the schedule by team names. /events/{id}/odds costs nothing when a game has no props, so every matched game is asked;
the budget guards are: stop before DAILY_CREDIT_CAP (Eastern date, counted in data/log/credits.csv) and stop at CREDIT_FLOOR remaining (the key is shared with the NBA project).
One row per (game, book, market, player, point) with the Over and Under prices side by side. Names are matched to ESPN later; team names here go through team_aliases.csv.
"""
import os, sys, csv, json, time, argparse, difflib, datetime as dt
from zoneinfo import ZoneInfo
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, LOG = os.path.join(ROOT, "data", "raw"), os.path.join(ROOT, "data", "log")
BASE = "https://api.the-odds-api.com/v4"
ET = ZoneInfo("America/New_York")
COLS = ["pulled_at", "odds_event", "espn_event", "commence", "home", "away", "book", "market", "player", "point", "over", "under", "last_update"]


def norm_team(n):
    """'Montana St Bobcats' (Odds API) -> 'montana state bobcats' (ESPN); aliases from data/raw/team_aliases.csv are applied first."""
    n = " " + (n or "").lower().replace(".", "").replace("&", "and").replace("'", "") + " "
    for a, b in ((" st ", " state "), (" univ ", " university "), (" intl ", " international ")):
        n = n.replace(a, b)
    return " ".join(n.split())


def load_aliases():
    p = os.path.join(RAW, "team_aliases.csv"); out = {}
    if os.path.exists(p):
        with open(p, newline="") as f:
            for r in csv.DictReader(f): out[norm_team(r["odds_name"])] = norm_team(r["espn_name"])
    return out


def match_events(odds_events, schedule, aliases):
    """Odds API event -> ESPN schedule row by normalised team names (home and away, either spelling through the aliases) and a start time within 3 hours."""
    key = lambda n: aliases.get(norm_team(n), norm_team(n))
    sched = {}
    for r in schedule: sched.setdefault((key(r["home"]), key(r["away"])), []).append(r)
    out, unmatched = [], []
    for e in odds_events:
        rows = sched.get((key(e["home_team"]), key(e["away_team"])), [])
        t = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
        hit = [r for r in rows if abs((dt.datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00")) - t).total_seconds()) < 3 * 3600]
        if hit: out.append((e, hit[0]))
        else: unmatched.append(e)
    return out, unmatched


def suggest_for_unmatched(sched_rows, odds_unmatched, aliases):
    """For each in-scope ESPN game with no Odds API event, the closest unmatched Odds API events (starting within 3 hours, ranked by how alike the home and away names are)
    and the alias rows (odds_name,espn_name) that would join them. A game against a non-Division I team has no sensible candidate and gets none."""
    key = lambda n: aliases.get(norm_team(n), norm_team(n))
    sim = lambda a, b: difflib.SequenceMatcher(None, key(a), key(b)).ratio()
    out = []
    for x in sched_rows:
        t0 = dt.datetime.fromisoformat(x["start_utc"].replace("Z", "+00:00")); cands = []
        for e in odds_unmatched:
            t = dt.datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
            if abs((t - t0).total_seconds()) >= 3 * 3600: continue
            sh, sa = sim(e["home_team"], x["home"]), sim(e["away_team"], x["away"])
            if sh + sa >= 1.4 and min(sh, sa) >= 0.5: cands.append((sh + sa, e, sh, sa))
        cands.sort(key=lambda c: -c[0])
        row = {"espn_event": x["event"], "start_utc": x["start_utc"], "espn_away": x["away"], "espn_home": x["home"], "candidates": "", "suggested_aliases": ""}
        if cands:
            row["candidates"] = " | ".join(f"{c[1]['away_team']} @ {c[1]['home_team']} ({c[0] / 2:.2f})" for c in cands[:3])
            e, sh, sa = cands[0][1], cands[0][2], cands[0][3]
            adds = []
            if key(e["home_team"]) != key(x["home"]): adds.append(f"{e['home_team']},{x['home']}")
            if key(e["away_team"]) != key(x["away"]): adds.append(f"{e['away_team']},{x['away']}")
            row["suggested_aliases"] = " ; ".join(adds)
        out.append(row)
    return out


def log_unmatched(rows, now):
    """data/log/unmatched_events.csv: one row per ESPN game that had no Odds API event, first time it is seen (append only), so the aliases can be added from one place."""
    path = os.path.join(LOG, "unmatched_events.csv"); seen = set()
    cols = ["first_seen", "espn_event", "start_utc", "espn_away", "espn_home", "candidates", "suggested_aliases"]
    if os.path.exists(path):
        with open(path, newline="") as f: seen = {r["espn_event"] for r in csv.DictReader(f)}
    new = [[now.isoformat(timespec="seconds"), r["espn_event"], r["start_utc"], r["espn_away"], r["espn_home"], r["candidates"], r["suggested_aliases"]] for r in rows if r["espn_event"] not in seen]
    if new: append(path, cols, new)
    return new


def parse_odds(j, espn_event, pulled_at):
    """One /odds answer -> rows with Over and Under prices side by side."""
    rows = []
    for b in j.get("bookmakers", []):
        for m in b.get("markets", []):
            if m["key"] not in C.MARKET_STAT: continue
            by = {}
            for o in m.get("outcomes", []):
                k = (o.get("description"), o.get("point")); by.setdefault(k, {})[o.get("name")] = o.get("price")
            for (player, point), px in by.items():
                rows.append([pulled_at, j.get("id"), espn_event, j.get("commence_time"), j.get("home_team"), j.get("away_team"), b["key"], m["key"], player, point,
                             px.get("Over"), px.get("Under"), m.get("last_update") or b.get("last_update")])
    return rows


def credits_today(path):
    if not os.path.exists(path): return 0.0
    today = dt.datetime.now(ET).date().isoformat(); tot = 0.0
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["et_date"] == today:
                try: tot += float(r["used"])
                except ValueError: pass
    return tot


def append(path, header, rows):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--hours", type=float, default=C.LINES_HORIZON_HOURS); ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args()
    key = os.environ.get("ODDS_API_KEY")
    if not key: sys.exit("no ODDS_API_KEY")
    os.makedirs(LOG, exist_ok=True); s = requests.Session()
    with open(os.path.join(RAW, "schedule.csv"), newline="") as f: sched = [r for r in csv.DictReader(f) if r["in_scope"] == "1"]
    now = dt.datetime.now(dt.timezone.utc)
    sched = [r for r in sched if now - dt.timedelta(minutes=5) <= dt.datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00")) <= now + dt.timedelta(hours=a.hours)]
    r = s.get(f"{BASE}/sports/{C.SPORT}/events", params={"apiKey": key, "dateFormat": "iso"}, timeout=30); r.raise_for_status()
    left = float(r.headers.get("x-requests-remaining", "nan"))
    matched, unmatched = match_events(r.json(), sched, load_aliases())
    print(f"in-scope games starting within {a.hours:g}h: {len(sched)}; matched to Odds API events: {len(matched)}; credits left {left:g}")
    sched_ids = {m[1]["event"] for m in matched}
    miss = [x for x in sched if x["event"] not in sched_ids]
    sug = {r["espn_event"]: r for r in suggest_for_unmatched(miss, unmatched, load_aliases())}
    for x in miss:
        sg = sug[x["event"]]
        print(f"  no Odds API event for {x['away']} @ {x['home']} ({x['start_utc']}): " + (f"closest Odds API event {sg['candidates']}; alias rows: {sg['suggested_aliases'] or 'none needed'}" if sg["candidates"] else "no close Odds API event (likely a non-Division I opponent)"))
    if not a.dry_run:
        os.makedirs(LOG, exist_ok=True); log_unmatched(list(sug.values()), now)
    if a.dry_run: return
    credlog = os.path.join(LOG, "credits.csv"); pulled_at = now.isoformat(timespec="seconds"); rows_all = []; used_total = 0.0
    for e, row in matched:
        spent = credits_today(credlog)
        if spent + C.EST_CREDITS_PER_GAME > C.DAILY_CREDIT_CAP: print(f"daily cap {C.DAILY_CREDIT_CAP} reached ({spent:g} spent): stopping"); break
        if left == left and left - C.EST_CREDITS_PER_GAME < C.CREDIT_FLOOR: print(f"credit floor {C.CREDIT_FLOOR} reached ({left:g} left): stopping"); break
        rr = s.get(f"{BASE}/sports/{C.SPORT}/events/{e['id']}/odds", timeout=40, params={"apiKey": key, "bookmakers": ",".join(C.ODDS_BOOKS), "markets": ",".join(C.MARKET_STAT),
                                                                                    "oddsFormat": "american", "dateFormat": "iso"})
        if rr.status_code in (401, 429): sys.exit(f"Odds API {rr.status_code}: {rr.text[:200]}")
        if not rr.ok: print(f"  {e['away_team']} @ {e['home_team']}: {rr.status_code}"); continue
        used = float(rr.headers.get("x-requests-last", 0) or 0); left = float(rr.headers.get("x-requests-remaining", "nan")); used_total += used
        append(credlog, ["ts", "et_date", "odds_event", "game", "used", "left"], [[pulled_at, dt.datetime.now(ET).date().isoformat(), e["id"], f"{e['away_team']} @ {e['home_team']}", used, left]])
        rows = parse_odds(rr.json(), row["event"], pulled_at); rows_all += rows
        print(f"  {e['away_team']} @ {e['home_team']}: {len(rows)} lines, {used:g} credits")
        time.sleep(0.3)
    latest = os.path.join(RAW, "lines.csv"); old = {}
    if os.path.exists(latest):
        with open(latest, newline="") as f:
            for r in csv.DictReader(f): old[(r["odds_event"], r["book"], r["market"], r["player"], r["point"])] = r
    changed = []
    for r in rows_all:
        k = (r[1], r[6], r[7], r[8], str(r[9])); o = old.get(k)
        if not o or (o["over"], o["under"]) != (str(r[10] if r[10] is not None else ""), str(r[11] if r[11] is not None else "")): changed.append(r)
        old[k] = dict(zip(COLS, [("" if v is None else v) for v in r]))
    if changed: append(os.path.join(LOG, "lines_log.csv"), COLS, changed)
    with open(latest, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(old.values())
    print(f"lines: {len(rows_all)} fetched, {len(changed)} new or moved; credits used this run {used_total:g}; left {left:g}")


if __name__ == "__main__":
    main()
