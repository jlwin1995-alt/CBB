"""Team -> conference -> tier table for every Division I team  ->  data/raw/team_tiers.csv

    python pipeline/build_tiers.py

ESPN's team pages carry the conference id (groups.id), and the core API names it, so this covers all 362 Division I teams (the groups endpoint used by the first probe only
listed 289). Tiers follow pipeline/config.py: power 6, mid-major, everything else low-major. Names that the config lists but ESPN spells differently show up in the printed check.
"""
import os, sys, csv, time
import requests
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball/groups"
S = requests.Session()


def get(url, params=None, tries=4):
    for t in range(tries):
        try:
            r = S.get(url, params=params, timeout=40)
            if r.status_code == 200: return r.json()
        except Exception: pass
        time.sleep(1.5 * (t + 1))
    return None


def tier(conf):
    c = (conf or "").replace(" Conference", "").strip()
    if c in C.POWER6: return "power6"
    if c in C.MID_MAJOR: return "mid"
    return "low"


def main():
    teams = get(B + "/teams", {"groups": "50", "limit": "500"})["sports"][0]["leagues"][0]["teams"]
    ids = [t["team"] for t in teams]
    def one(t):
        d = get(f"{B}/teams/{t['id']}")
        g = ((d or {}).get("team") or {}).get("groups") or {}
        return t, str(g.get("id", ""))
    with ThreadPoolExecutor(12) as ex: res = list(ex.map(one, ids))
    names = {}
    for gid in sorted({g for _, g in res if g}):
        j = get(f"{CORE}/{gid}")
        names[gid] = (j or {}).get("name") or (j or {}).get("shortName") or ""
    rows = []
    for t, gid in res:
        conf = names.get(gid, "").replace(" Conference", "")
        if conf == "NCAA Division I": conf = "American"      # ESPN parks the 13 American Athletic teams directly under the Division I root group (id 50)
        rows.append([t["id"], t.get("displayName"), t.get("abbreviation"), gid, conf, tier(conf)])
    os.makedirs(os.path.join(ROOT, "data", "raw"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "raw", "team_tiers.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["team_id", "team", "abbr", "conf_id", "conference", "tier"]); w.writerows(sorted(rows, key=lambda r: (r[5], r[4], r[1])))
    from collections import Counter
    print("teams", len(rows), "tiers", dict(Counter(r[5] for r in rows)))
    byconf = Counter(r[4] for r in rows)
    for c in C.POWER6 + C.MID_MAJOR:
        print(f"  {c:30s} {byconf.get(c, 0)}" + ("   <-- not found: check the name" if byconf.get(c, 0) == 0 else ""))
    print("low-major conferences:", sorted(c for c in byconf if tier(c) == "low"))
    print("teams with no conference name:", [r[1] for r in rows if not r[4]])


if __name__ == "__main__":
    main()
