# cbb: college basketball player projections, lines and grading

Separate project (own repo) from the NBA (`jlwin1995-alt/Bball`) and football work. Scope: **power 6 + mid-major conferences, Division I only**.
Odds API budget: **100 credits/day** (`pipeline/config.py`), on the **same key as the NBA project** (the user chose this on Nov 3, 2026 over a free 500-credit key). The pool is shared, so pulls stop when the remaining credits drop to **5,000** (`CREDIT_FLOOR`), which keeps the NBA project funded. At about 8 credits a game with props that is about 12 games a day.

## Where things stand (Nov 3, 2026)
* **Data:** four seasons of ESPN Division I box scores (2022-23 .. 2025-26, about 500k player-games) in `data/raw/`, plus the recruit classes 2023-26 and the 2026 transfer-portal list in `data/raw/recruits/`.
* **Backtest (walk-forward, research/):** version 0 (minutes x shrunk per-minute rates) ties a player's season-to-date average on fantasy points (FP MAE 7.27 vs 7.26) and is slightly better on minutes late in the season (4.90 vs 5.31 at 21+ games). A recruit-rank prior removes the minutes bias for top-25 freshmen (-2.2 -> -0.9) but moves overall error little (only ~9% of newcomer player-games are ranked recruits). A 200-minute team budget hurts when absences are unknown (minutes MAE 5.31 -> 5.64 / 6.21) and gains little even when they are known (5.11). Keep: recruit prior + no projection for unranked newcomers until 3 games.
* **Lines:** The Odds API `basketball_ncaab` has player props for marquee games only (probe #1: 1 of 4 sampled games; PrizePicks 9 points / 3 rebounds / 1 assists lines). Probe #2 (a full evening slate) decides the daily volume.

## Plan (phases and gates)
| Phase | What | Gate |
|---|---|---|
| 3a | ingest, tiers, lines pull for tomorrow | probe #2 shows enough props |
| 3b | model v1 (rank prior, newcomer cutoff), projections file, minimal site page | matches the backtest |
| 3c | line logging, grading, scorecard | one full day graded end to end |
| 3d | workflows + scheduled routines | a week without manual runs |
| 3e | calibration and bucket review at ~2,000 graded lines | any bucket clears 54.4% with a usable lower bound, else shelve |

Availability has no injury feed: infer it from the lines (a player with a line is expected to play), used only to decide who is shown, never to set a projection.

## Lines pull (phase 3a)
* `pipeline/fetch_lines.py` (run by `.github/workflows/lines.yml` every two hours in the evening, UTC): lists the Odds API's `basketball_ncaab` events (free), matches them to the in-scope games in `data/raw/schedule.csv` by team name (`data/raw/team_aliases.csv` holds spellings that differ), and asks `/odds` for points, rebounds, assists and threes from the seven sportsbooks plus PrizePicks. A game with no props costs 0 credits, so every in-scope game starting in the next 8 hours is asked; stops at the 100/day cap and at the 5,000-credit floor. Writes `data/raw/lines.csv` (latest) and `data/log/lines_log.csv` (every changed snapshot) and the spend to `data/log/credits.csv`.
* Needs the repository secret `ODDS_API_KEY`. `python pipeline/fetch_lines.py --dry-run` lists the matches and the games with no Odds API event (free).
* Probe #2 (Nov 3): 1 of 16 sampled games had props (Lipscomb @ Iowa), all power-6-vs-low-major games on an early-season night. Expect 10-20 PrizePicks lines on a typical early night, more on marquee nights and in conference play.

## Line grading (daily, automatic)
* `pipeline/grade_lines.py` (a step in `.github/workflows/lines.yml`, after the pull): keeps the last pull of each line (the closing line), grades it against the stored box scores once the game is final, and rewrites `data/log/lines_graded.csv` (one row per line: actual, minutes, result over / under / push / void / nomatch, plus `avg_prior`, the player's earlier-game average, as a model-free benchmark) and `data/log/lines_tally.json` (counts and Over rate overall, by market, by book, by date and for PrizePicks alone). Safe to run twice; the tally has no timestamp, so a run with nothing new commits nothing.
* This grades the **lines**, not a model: there is no CBB projection yet. A void is a player on the sheet with 0 minutes; `nomatch` means the game is final but the name was not found (the run prints a warning; fix with a name alias).
* First read (Nov 5-7, 130 closing lines, 128 decided): 66 Overs, 62 Unders (51.6%); points 43 of 78 Over, assists 5 of 14.

## Layout
* `pipeline/backfill_espn.py`: resumable ESPN box-score backfill, `python pipeline/backfill_espn.py 2026` (season = ending year)
* `pipeline/recruits.py`: recruit-rank priors learned from earlier classes only (walk-forward)
* `pipeline/config.py`: scope, credit cap, break-even
* `research/`: backtests and scoring scripts (`backtest.py`, `backtest2.py`, `score*.py`); outputs go to `research/out/` (not committed)
