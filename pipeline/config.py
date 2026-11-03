"""CBB project settings (separate from the NBA / football projects)."""
DAILY_CREDIT_CAP = 100          # The Odds API credits this project may spend per day (set by the user Nov 3, 2026)
SPORT = "basketball_ncaab"
ODDS_MARKETS = ["player_points", "player_rebounds", "player_assists", "player_threes"]
PP_BREAKEVEN = 0.544            # the user's break-even for PrizePicks legs
# Scope (user, Nov 3, 2026): power 6 + mid-major conferences, Division I only. Names are ESPN's conference table names.
POWER6 = ["Atlantic Coast", "Big 12", "Big East", "Big Ten", "Southeastern", "Pac-12"]
MID_MAJOR = ["Mountain West", "American", "Atlantic 10", "West Coast", "Missouri Valley", "Sun Belt", "Conference USA", "Mid-American", "Coastal Athletic Association", "Big West"]
# ESPN's table has no West Coast / Sun Belt / Southern / Southland / WAC / Summit / SWAC teams: classify those by hand in data/raw/team_tiers.csv
SCORING = {"pts": 1.0, "reb": 1.2, "ast": 1.5, "stl": 3.0, "blk": 3.0, "tov": -1.0}   # PrizePicks fantasy score
