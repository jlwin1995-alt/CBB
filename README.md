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
* Games with no Odds API event are listed in the run log with the closest unmatched Odds API event (start within 3 hours, ranked by name similarity) and the alias rows that would join them, and each is written once to `data/log/unmatched_events.csv` (`suggested_aliases` are `odds_name,espn_name` pairs for `data/raw/team_aliases.csv`; a non-Division I opponent has no candidate and needs nothing).
* Needs the repository secret `ODDS_API_KEY`. `python pipeline/fetch_lines.py --dry-run` lists the matches and the games with no Odds API event (free).
* Probe #2 (Nov 3): 1 of 16 sampled games had props (Lipscomb @ Iowa), all power-6-vs-low-major games on an early-season night. Expect 10-20 PrizePicks lines on a typical early night, more on marquee nights and in conference play.

## Line grading (daily, automatic)
* `pipeline/grade_lines.py` (a step in `.github/workflows/lines.yml`, after the pull): keeps the last pull of each line (the closing line), grades it against the stored box scores once the game is final, and rewrites `data/log/lines_graded.csv` (one row per line: actual, minutes, result over / under / push / void / nomatch, plus `avg_prior`, the player's earlier-game average, as a model-free benchmark) and `data/log/lines_tally.json` (counts and Over rate overall, by market, by book, by date and for PrizePicks alone). Safe to run twice; the tally has no timestamp, so a run with nothing new commits nothing.
* This grades the **lines**, not a model: there is no CBB projection yet. A void is a player on the sheet with 0 minutes; `nomatch` means the game is final but the name was not found (the run prints a warning; fix with a name alias).
* First read (Nov 5-7, 112 PrizePicks closing lines, 110 decided): 56 Overs, 54 Unders (50.9%).

## Projections (phase 3b)
* `pipeline/model.py`: expected minutes x shrunk per-minute rates x opponent (points, threes) x pace, with the recruit-rank prior for true freshmen, no projection for an unranked newcomer until 3 games, no 200-minute budget, and a linear un-shrink on points / assists / threes (`CAL`, fitted on 2026, checked on 2025).
* `pipeline/project.py` (a step in `lines.yml`, after the pull): projects every rostered player in the in-scope games starting in the next 36 hours (rosters are ESPN's current rosters, so transfers are on the right team) and writes `data/proj/projections.csv` (current) and `data/log/proj_log.csv`. A game's rows are replaced on every run until it starts and frozen after, so the log holds the last projection made before tip. DraftKings spread and total come from ESPN's free game page and are stored beside each projection (about a third of games have them); they are **not** model inputs yet.
* **Only PrizePicks lines are graded and shown** (user, Nov 8); the sportsbooks' closing lines for the same player and market become a **consensus** (median point, number of books): `lines_graded.csv` carries `consensus`, `n_books` and `vs_cons` (PrizePicks point minus consensus), and the tally has a `by_consensus_gap` block (PrizePicks below / level with / above the consensus). Sportsbooks post props for the marquee games only, so far 9 of 112 graded PrizePicks lines had a consensus. The pull still asks for all books, since the consensus needs them.
* `grade_lines.py` joins the log: `lines_graded.csv` gains `proj`, `edge` (projection minus line) and `pick`, and `lines_tally.json` gains a `model` block (hit rate of the favoured side, by market and by size of edge).
* Backtest, `research/validate_model.py` (roster = who played, so availability is known): 2026 Dec-Mar FP MAE 6.75 vs 6.70 for the season-to-date average (a tie), minutes MAE 5.09 vs 5.18; 2025 holdout 6.56 vs 6.53 and 5.06 vs 5.15. Nov 5-30 (when the average has little to go on): FP MAE 7.13 vs 7.33 (2026), 7.05 vs 7.31 (2025), but minutes MAE 5.67 vs 5.13 and a bias of -0.8 to -1.2 fantasy points before the un-shrink.
* Retro check on the 130 lines graded so far, `research/retro_lines.py` (history before each game, actual box-score rosters): the favoured side won 42 of 100 PrizePicks lines (42%) and projections run about 1.1 below the lines while the games finished about 0.8 above them. 110 lines on 16 marquee games over three days is noise-sized, but the gap is larger than the backtest bias for a team's top scorers (+0.1 to +1.4 points raw), so treat the model as **unproven against the lines** until the 3e review (about 2,000 graded lines).

## Site (board and scorecard)
* `site/` is a static page (vanilla JS, no build tooling) with two tabs. **Board:** PrizePicks lines for games not yet graded, each with the sportsbook consensus (median of the other books, hover for each book's number), the model projection from the pre-tip log, the edge and the side it favours; filters for market, edge size, consensus-only and player. **Scorecard:** PrizePicks lines vs results overall and by market, against the consensus gap, by day, the model's hit rate with 95% ranges once projections are graded, the backtest table, and the latest graded lines.
* `pipeline/build_site.py` writes `site/data/board.json` and `site/data/scorecard.json` from `data/` (not committed). The last steps of `lines.yml` build it and publish `site/` to GitHub Pages; they are non-fatal, so a Pages problem never stops the lines from being committed. **One-time setup:** repository Settings > Pages > Source: GitHub Actions.
* Preview locally: `python pipeline/build_site.py && cd site && python -m http.server`.

## Layout
* `pipeline/backfill_espn.py`: resumable ESPN box-score backfill, `python pipeline/backfill_espn.py 2026` (season = ending year)
* `pipeline/recruits.py`: recruit-rank priors learned from earlier classes only (walk-forward)
* `pipeline/config.py`: scope, credit cap, break-even
* `research/`: backtests and scoring scripts (`backtest.py`, `backtest2.py`, `score*.py`); outputs go to `research/out/` (not committed)
