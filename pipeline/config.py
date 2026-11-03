"""CBB project settings (separate from the NBA / football projects)."""
DAILY_CREDIT_CAP = 100          # The Odds API credits this project may spend per day (set by the user Nov 3, 2026)
# The user chose (Nov 3, 2026) to run this project on the SAME Odds API key as the NBA project (about 19,000 credits, NBA spends roughly 100-150 a day), not a free 500-credit key.
# Because the pool is shared, CBB stops pulling when the remaining-credits header drops to CREDIT_FLOOR, which keeps the NBA project funded.
CREDIT_FLOOR = 5000
SPORT = "basketball_ncaab"
# Credits per game are (markets x bookmaker groups): probe #1 spent 8 credits on a game with props for these four markets (0 when a game has no props).
ODDS_MARKETS = ["player_points", "player_rebounds", "player_assists", "player_threes"]
# Same book list as the NBA project: the seven sportsbooks plus PrizePicks. The Odds API bills 10 bookmakers as one group, so 8 books cost (markets x 1) credits a game
# (the first probe, which asked for 12 books, paid 8 for four markets). A game with no props costs 0, so scanning every in-scope game is free.
ODDS_BOOKS = ["draftkings", "fanduel", "betmgm", "williamhill_us", "betrivers", "espnbet", "fanatics", "prizepicks"]
DFS_BOOKS = ["prizepicks", "underdog", "pick6", "dabble_us_dfs"]
MARKET_STAT = {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast", "player_threes": "fg3m"}
EST_CREDITS_PER_GAME = 4        # four markets x one bookmaker group; used to stop before the daily cap is passed
LINES_HORIZON_HOURS = 8         # only games starting within this many hours are priced
PP_BREAKEVEN = 0.544            # the user's break-even for PrizePicks legs
# Scope (user, Nov 3, 2026): power 6 + mid-major conferences, Division I only. Names are ESPN's conference table names.
POWER6 = ["Atlantic Coast", "Big 12", "Big East", "Big Ten", "Southeastern", "Pac-12"]
MID_MAJOR = ["Mountain West", "American", "Atlantic 10", "West Coast", "Missouri Valley", "Sun Belt", "Conference USA", "Mid-American", "Coastal Athletic Association", "Big West"]
# ESPN's table has no West Coast / Sun Belt / Southern / Southland / WAC / Summit / SWAC teams: classify those by hand in data/raw/team_tiers.csv
SCORING = {"pts": 1.0, "reb": 1.2, "ast": 1.5, "stl": 3.0, "blk": 3.0, "tov": -1.0}   # PrizePicks fantasy score
