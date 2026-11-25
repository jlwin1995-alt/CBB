"""When should the lines workflow be dispatched today?  A plan built from the day's schedule, so refreshes land just before each wave of tip-offs instead of waiting on GitHub's own hourly schedule.

    python pipeline/plan_refreshes.py                      # today (Eastern), from now
    python pipeline/plan_refreshes.py --date 2026-11-27    # another ET date (holiday weeks start games at 10am ET)
    python pipeline/plan_refreshes.py --json               # machine-readable

Why: the odds pull only prices games starting within `--hours` of the run (fetch_lines.py) and costs credits per game, with a daily cap (config.DAILY_CREDIT_CAP). The cron's hourly runs all use the
8-hour default, so every run re-prices the same games and the cap is gone by mid-afternoon on a busy day, while the games that tip first are priced late or not at all. This plan instead gives each WAVE of tip-offs
one pull, started LEAD_MIN before its first tip (props are usually up by then), with a horizon just long enough to cover that wave (so the next wave is not priced early). A free grading refresh (horizon 0: ingest,
grade, project, build, no pricing) follows the last tip of the day.

A wave = the first tip not yet in a wave, plus every game that tips within WAVE_MIN after it. Times are UTC ISO strings; `hours` is the value for the workflow's `hours` input.
"""
import os, sys, json, argparse, datetime as dt
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

WAVE_MIN = 120            # games tipping within this many minutes of a wave's first tip share one pull
LEAD_MIN = 130            # dispatch this long before the wave's first tip
GRADE_AFTER_MIN = 180     # a free grading refresh this long after the last tip of the day
LATE_GRADE_MIN = 150      # ... and one this long after each wave's last tip when the next wave is more than that far away
EST_CREDITS = C.EST_CREDITS_PER_GAME


def plan(date_et, now, wave_min=WAVE_MIN, lead_min=LEAD_MIN):
    s = pd.read_csv(os.path.join(ROOT, "data", "raw", "schedule.csv"))
    s = s[(s.in_scope == 1) & (s.et_date == date_et)].copy()
    s["t"] = pd.to_datetime(s.start_utc, utc=True)
    s = s.sort_values("t")
    waves, i = [], 0
    tips = list(s.t)
    while i < len(tips):
        start = tips[i]; j = i
        while j + 1 < len(tips) and tips[j + 1] < start + pd.Timedelta(minutes=wave_min): j += 1
        waves.append({"first": start, "last": tips[j], "games": j - i + 1}); i = j + 1
    rows = []
    for w in waves:
        at = w["first"] - pd.Timedelta(minutes=lead_min)
        hours = round((w["last"] - at).total_seconds() / 3600 + 0.1, 2)
        rows.append({"kind": "pull", "at": at, "hours": hours, "games": w["games"], "first_tip": w["first"], "last_tip": w["last"]})
    if waves:
        end = waves[-1]["last"]
        rows.append({"kind": "grade", "at": end + pd.Timedelta(minutes=GRADE_AFTER_MIN), "hours": 0, "games": 0, "first_tip": end, "last_tip": end})
    for k in range(len(waves) - 1):                                         # a quiet gap between waves: grade what has finished
        gap = (waves[k + 1]["first"] - waves[k]["last"]).total_seconds() / 60
        if gap > LATE_GRADE_MIN + LEAD_MIN: rows.append({"kind": "grade", "at": waves[k]["last"] + pd.Timedelta(minutes=LATE_GRADE_MIN), "hours": 0, "games": 0, "first_tip": waves[k]["last"], "last_tip": waves[k]["last"]})
    rows.sort(key=lambda r: r["at"])
    for r in rows:
        r["status"] = "due now" if r["at"] <= now and (r["kind"] == "grade" or r["last_tip"] > now) else ("past" if r["at"] <= now else "scheduled")
    return rows, len(s)


def spent_today(date_et):
    p = os.path.join(ROOT, "data", "log", "credits.csv")
    if not os.path.exists(p): return 0.0
    c = pd.read_csv(p)
    return float(c[c.et_date == date_et].used.sum())


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--date"); ap.add_argument("--now"); ap.add_argument("--json", action="store_true"); a = ap.parse_args()
    now = pd.Timestamp(a.now, tz="UTC") if a.now else pd.Timestamp.now("UTC")
    date_et = a.date or now.tz_convert("America/New_York").date().isoformat()
    rows, n = plan(date_et, now)
    spent = spent_today(date_et); est = sum(r["games"] for r in rows if r["kind"] == "pull") * EST_CREDITS
    if a.json:
        print(json.dumps({"date": date_et, "games": n, "spent": spent, "cap": C.DAILY_CREDIT_CAP, "upper_bound_credits": est,
                          "rows": [{**{k: v for k, v in r.items() if k not in ("at", "first_tip", "last_tip")}, "at": r["at"].strftime("%Y-%m-%dT%H:%MZ"),
                                    "first_tip": r["first_tip"].strftime("%H:%MZ"), "last_tip": r["last_tip"].strftime("%H:%MZ")} for r in rows]}, indent=1)); return
    print(f"{date_et} (ET): {n} in-scope games in {sum(r['kind'] == 'pull' for r in rows)} waves; credits spent today {spent:g} of cap {C.DAILY_CREDIT_CAP:g}; "
          f"if every game had props the plan would price {est:g} (4 per game with props, 0 for games without)")
    for r in rows:
        tip = f"{r['first_tip']:%H:%MZ}" + (f"-{r['last_tip']:%H:%MZ}" if r["last_tip"] != r["first_tip"] else "")
        et = r["at"].tz_convert("America/New_York")
        print(f"  {r['at']:%Y-%m-%dT%H:%MZ} ({et:%-I:%M%p} ET)  {r['kind']:5} hours={r['hours']:<5g} {('%d games tipping %s' % (r['games'], tip)) if r['kind'] == 'pull' else ('after the last tip ' + f'{r['last_tip']:%H:%MZ}')}  [{r['status']}]")


if __name__ == "__main__":
    main()
