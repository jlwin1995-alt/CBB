# cbb: college basketball player projections, lines and grading

Separate project (own repo) from the NBA (`jlwin1995-alt/Bball`) and football work. Scope: **power 6 + mid-major conferences, Division I only**.
Daily Odds API budget: **100 credits/day** (`pipeline/config.py`).

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

## Layout
* `pipeline/backfill_espn.py`: resumable ESPN box-score backfill, `python pipeline/backfill_espn.py 2026` (season = ending year)
* `pipeline/recruits.py`: recruit-rank priors learned from earlier classes only (walk-forward)
* `pipeline/config.py`: scope, credit cap, break-even
* `research/`: backtests and scoring scripts (`backtest.py`, `backtest2.py`, `score*.py`); outputs go to `research/out/` (not committed)
