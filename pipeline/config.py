"""CBB project settings (separate from the NBA / football projects)."""
DAILY_CREDIT_CAP = 100          # The Odds API credits this project may spend per day (set by the user Nov 3, 2026)
TOTAL_CREDIT_BUDGET = 500       # this project has its own FREE key: 500 credits in total (user, Nov 3, 2026), about 5 days at the daily cap
CREDIT_FLOOR = 25               # stop pulling when the remaining-credits header drops to this, so the key is never run dry mid-pull
SPORT = "basketball_ncaab"
# Credits per game are (markets x bookmaker groups): probe #1 spent 8 for four markets across the books + DFS groups, so about 2 per market. On a 500-credit key the
# default is POINTS ONLY (the market PrizePicks posts most often): about 250 games instead of about 60. Widen it once the key (or the credit budget) allows.
ODDS_MARKETS = ["player_points"]
ODDS_MARKETS_FULL = ["player_points", "player_rebounds", "player_assists", "player_threes"]
PP_BREAKEVEN = 0.544            # the user's break-even for PrizePicks legs
# Scope (user, Nov 3, 2026): power 6 + mid-major conferences, Division I only. Names are ESPN's conference table names.
POWER6 = ["Atlantic Coast", "Big 12", "Big East", "Big Ten", "Southeastern", "Pac-12"]
MID_MAJOR = ["Mountain West", "American", "Atlantic 10", "West Coast", "Missouri Valley", "Sun Belt", "Conference USA", "Mid-American", "Coastal Athletic Association", "Big West"]
# ESPN's table has no West Coast / Sun Belt / Southern / Southland / WAC / Summit / SWAC teams: classify those by hand in data/raw/team_tiers.csv
SCORING = {"pts": 1.0, "reb": 1.2, "ast": 1.5, "stl": 3.0, "blk": 3.0, "tov": -1.0}   # PrizePicks fantasy score
