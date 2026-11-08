"""CBB projection model v1: expected minutes x shrunk per-minute rates x opponent (points, threes) x pace.  Pure functions over DataFrames.

This is research/backtest2.py (version 0 plus the recruit-rank prior for true freshmen) in reusable form, with the backtest's findings applied:
  * recruit-rank prior for newcomers (no earlier D1 record), learned only from classes whose first season is before this one;
  * an UNRANKED newcomer is not projected until he has NEWCOMER_MIN_GAMES games this season (the model has nothing to go on);
  * no 200-minute team budget (it hurt when absences are unknown).
Spread and total are NOT inputs: they are logged beside each projection (project.py) so they can be tested once there are enough graded lines.

box: player-game rows (pid, team_id, event, date, min, pts, ...) for the season and the two before it, with columns 'season'.
games: games_<season>.csv rows for the same seasons (home_id, away_id, neutral, scores).
"""
import numpy as np, pandas as pd
from scipy import sparse
from scipy.sparse.linalg import lsqr

STATS = ["pts", "reb", "ast", "stl", "blk", "tov", "fg3m"]
SCORING = {"pts": 1.0, "reb": 1.2, "ast": 1.5, "stl": 3.0, "blk": 3.0, "tov": -1.0}
NEWCOMER_MIN_GAMES = 3
RATE_K = 100.0              # minutes of league-average play each player's rate is shrunk toward
MIN_PRIOR_GAMES = 2.0       # pseudo-games of last season's minutes blended into this season's recent minutes
RECENT_N = 6                # recent-minutes window (games)
SEASON_W = (1.0, 0.5, 0.2)  # weights for rates: this season, last, two back
LAM = 60.0                  # ridge penalty for team ratings
# Un-shrink: actual = a + b x projection, fitted on the 2026 season walk-forward (research/validate_model.py 2026) and checked on 2025 as a holdout, where it takes the
# rotation-player bias (min >= 20) from -0.67 to +0.02 points and fantasy-point MAE from 6.56 to 6.54. Rebounds, steals, blocks and turnovers fit at slope ~1, so they are untouched.
CAL = {"pts": (1.125, -0.581), "ast": (1.106, -0.075), "fg3m": (1.083, -0.021)}


def prep(box, games):
    """numeric columns, played minutes only, one row per (event, pid); games with both teams seen in 8+ games (drops one-off non-D1 opponents)."""
    P = box.copy()
    for c in ["min", "pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pf", "oreb", "dreb"]:
        P[c] = pd.to_numeric(P[c], errors="coerce")
    P = P.dropna(subset=["min"]); P = P[P["min"] > 0]
    P["date"] = pd.to_datetime(P["date"])
    G = games.copy(); G["date"] = pd.to_datetime(G["date"]); G = G.drop_duplicates("event"); P = P.drop_duplicates(["event", "pid"])
    cnt = pd.concat([G.home_id, G.away_id]).value_counts(); d1 = set(cnt[cnt >= 8].index)
    G = G[G.home_id.isin(d1) & G.away_id.isin(d1)]
    P = P[P.event.isin(set(G.event))]
    T = P.groupby(["event", "team_id"]).agg(pts=("pts", "sum"), fga=("fga", "sum"), oreb=("oreb", "sum"), tov=("tov", "sum"), fta=("fta", "sum")).reset_index()
    T["poss"] = T.fga - T.oreb + T.tov + 0.475 * T.fta
    G = (G.merge(T.rename(columns={c: "h_" + c for c in T.columns if c != "event"}), left_on=["event", "home_id"], right_on=["event", "h_team_id"], how="left")
          .merge(T.rename(columns={c: "a_" + c for c in T.columns if c != "event"}), left_on=["event", "away_id"], right_on=["event", "a_team_id"], how="left"))
    G = G.dropna(subset=["h_poss", "a_poss"]); G["poss"] = (G.h_poss + G.a_poss) / 2
    return P, G


def ratings(G, season, upto):
    """ridge: points per 100 possessions = mu + off[team] - def[opp] + home advantage; last season's games count 0.4."""
    g = G[(G.date < upto) & (G.season >= season - 1)]
    w = np.where(g.season == season, 1.0, 0.4)
    teams = sorted(set(g.home_id) | set(g.away_id)); ix = {t: i for i, t in enumerate(teams)}; n = len(teams)
    rows, cols, vals, y, ww = [], [], [], [], []; r = 0
    for hid, aid, hp, ap, poss, neu, wt in zip(g.home_id, g.away_id, g.h_pts, g.a_pts, g.poss, g.neutral, w):
        for off, de, pts, hm in ((hid, aid, hp, 1), (aid, hid, ap, 0)):
            rows += [r, r, r]; cols += [ix[off], n + ix[de], 2 * n]; vals += [1, -1, (hm if not neu else 0)]; y.append(100 * pts / poss); ww.append(wt); r += 1
    A = sparse.csr_matrix((vals, (rows, cols)), shape=(r, 2 * n + 1)); yv = np.array(y); mu = yv.mean(); sw = np.sqrt(np.array(ww))
    sol = lsqr(sparse.diags(sw) @ A, sw * (yv - mu), damp=np.sqrt(LAM), atol=1e-6, btol=1e-6)[0]
    off = {t: sol[ix[t]] for t in teams}; de = {t: sol[n + ix[t]] for t in teams}
    pace = pd.concat([g.assign(t=g.home_id)[["t", "poss"]], g.assign(t=g.away_id)[["t", "poss"]]]).groupby("t").poss.mean()
    return mu, off, de, pace


def project(P, G, slate, season, asof, rank_tab=None, rank_cur=None):
    """slate: rows (event, team_id, opp_id, is_home, pid, pos) = who we project and against whom. History is P/G strictly before `asof`.
    rank_tab/rank_cur: recruit.learn(season) tables for the true freshmen. Returns one row per slate row with min_p and <stat>_p."""
    from recruits import bucket
    asof = pd.Timestamp(asof)
    H = P[P.date < asof].copy()
    mu, off, de, pace = ratings(G, season, asof); lp = pace.mean()
    H["w"] = np.select([H.season == season, H.season == season - 1], [SEASON_W[0], SEASON_W[1]], SEASON_W[2])
    for s in STATS: H[s + "_w"] = H[s] * H.w
    H["min_w"] = H["min"] * H.w
    agg = H.groupby("pid").agg(**{s + "_w": (s + "_w", "sum") for s in STATS}, min_w=("min_w", "sum"))
    posm = H.groupby("pos")[[s + "_w" for s in STATS] + ["min_w"]].sum()
    prior = {s: (posm[s + "_w"] / posm["min_w"]) for s in STATS}
    lg = {s: H[s + "_w"].sum() / H["min_w"].sum() for s in STATS}
    cur = H[H.season == season].sort_values("date"); prev = H[H.season == season - 1]; old = H[H.season == season - 2]
    recent = cur.groupby("pid").tail(RECENT_N).groupby("pid")["min"].mean(); ncur = cur.groupby("pid").size()
    pm = prev.groupby("pid")["min"].agg(["mean", "size"]); pm = pm[pm["size"] >= 8]["mean"]
    allprev = set(prev.pid) | set(old.pid)
    first = prev[~prev.pid.isin(set(old.pid))]; newc_min = first.groupby("pid")["min"].mean().mean() if len(first) else 12.0
    lastpos = H.sort_values("date").groupby("pid")["pos"].last()
    out = []
    for r in slate.itertuples():
        pid = r.pid; n = int(ncur.get(pid, 0)); newcomer = pid not in allprev
        bk = None
        pri = pm.get(pid, np.nan)
        if np.isnan(pri): pri = newc_min if newcomer else 10.0
        if newcomer and rank_tab is not None:
            bk = bucket(rank_cur[pid]) if (rank_cur and pid in rank_cur) else "unranked"
            if bk in rank_tab: pri = rank_tab[bk]["mpg"]
        rec = recent.get(pid, np.nan)
        mproj = (n * (rec if n else 0) + MIN_PRIOR_GAMES * pri) / (n + MIN_PRIOR_GAMES) if n else pri
        row = {"event": r.event, "team_id": r.team_id, "opp_id": r.opp_id, "pid": pid, "n_games": n, "newcomer": int(newcomer), "bucket": bk or "", "min_p": mproj}
        if newcomer and (bk in (None, "unranked")) and n < NEWCOMER_MIN_GAMES:
            row["note"] = "newcomer, unranked: no projection until 3 games"
            for s in STATS: row[s + "_p"] = np.nan
            row["min_p"] = np.nan; out.append(row); continue
        a = agg.loc[pid] if pid in agg.index else None
        pos = lastpos.get(pid, getattr(r, "pos", "G")); pos = pos if pos in prior["pts"].index else "G"
        mw = 0.0 if a is None else a.min_w
        dfac = 1.0
        if r.team_id in off and r.opp_id in de and mu + off[r.team_id] > 0:
            dfac = (mu + off[r.team_id] - de[r.opp_id]) / (mu + off[r.team_id])
        pf = (pace.get(r.team_id, lp) + pace.get(r.opp_id, lp)) / (2 * lp)
        for s in STATS:
            pr = prior[s].get(pos, lg[s]); num = 0.0 if a is None else a[s + "_w"]
            if bk is not None and rank_tab is not None and bk in rank_tab: pr = rank_tab[bk][s]
            rate = (num + RATE_K * pr) / (mw + RATE_K)
            v = mproj * rate * (dfac if s in ("pts", "fg3m") else 1.0) * pf
            if s in CAL: v = max(0.0, CAL[s][0] * v + CAL[s][1])
            row[s + "_p"] = v
        row["note"] = ""
        out.append(row)
    return pd.DataFrame(out)
