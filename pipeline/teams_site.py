"""Team comparison, unit strength, allowed-by-position and player consistency tags -> site/data/teams.json and site/data/consistency.json  (display only: nothing here feeds the projections)

    python pipeline/teams_site.py

teams.json: for every Division I team with 3+ box-scored games this season (teams in data/raw/team_tiers.csv; exhibition and non-D1 opponents are dropped from the table but their games still count
as the opposition's "allowed"), per-game stats FOR the team and ALLOWED (the opponent's totals in the same games) over the season and the last 3 games, league ranks, unit strength (what the team's
guards / forwards / centers produce per 40 minutes, ranked in thirds) and what each defence allows per minute to guards / forwards / centers against the league at that position.
There is NO schedule adjustment: with about five games a team, who it has played dominates (a power-6 team that has beaten three low-majors looks strong everywhere). Each team lists the tiers of
the opponents it has faced so the page can say so. Possessions = FGA - OREB + TOV + 0.475 FTA, the same estimate the model uses.

consistency.json: per player, over his last 20 games of 12+ minutes across this and last season (8 needed; most freshmen and transfers will not qualify until later in the season), the spread of
fantasy points (PrizePicks weights) and of points, rebounds and assists against players at a similar level (thirds of the stat's mean): Steady / Average / Volatile = bottom / middle / top third, with
Spiky / Dud-prone / Boom-bust for Volatile players from the share of games at 1.3x / 0.7x his own median. Same method as the NBA site (Bball pipeline/consistency.py).
"""
import os, sys, json
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, OUT = os.path.join(ROOT, "data", "raw"), os.path.join(ROOT, "site", "data")
SUMS = ["pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf"]
SC = {"pts": 1.0, "reb": 1.2, "ast": 1.5, "stl": 3.0, "blk": 3.0, "tov": -1.0}
POS = {"G": "G", "PG": "G", "SG": "G", "F": "F", "SF": "F", "PF": "F", "ATH": "F", "C": "C"}
MIN_TEAM_G = 3
WINDOWS = {"season": None, "l3": 3}
VS_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
LOWER_BETTER_FOR = {"tov", "pf"}


def load():
    p = pd.read_csv(os.path.join(RAW, "players_2027.csv.gz"), dtype={"pid": str})
    tt = pd.read_csv(os.path.join(RAW, "team_tiers.csv"))
    return p, tt


def team_games(p, tt):
    p = p[p["min"] > 0].copy()
    p["reb"] = p["oreb"] + p["dreb"]
    t = p.groupby(["event", "team_id", "date"], as_index=False)[SUMS].sum()
    ev = t.groupby("event").team_id.agg(lambda s: list(s))
    t = t[t["event"].map(lambda e: len(ev[e]) == 2)]                                   # both teams' box scores present
    o = t[["event", "team_id"] + SUMS].rename(columns={"team_id": "opp_id", **{k: k + "_o" for k in SUMS}})
    t = t.merge(o, on="event"); t = t[t.team_id != t.opp_id]
    t["poss"] = t.fga - t.oreb + t.tov + 0.475 * t.fta
    t["poss_o"] = t.fga_o - t.oreb_o + t.tov_o + 0.475 * t.fta_o
    t["win"] = (t.pts > t.pts_o).astype(int)
    d1 = set(tt.team_id)
    t = t[t.team_id.isin(d1)]
    return t.sort_values(["date", "event"]), p


def side(d, sfx):
    m = {k: round(float(d[k + sfx].mean()), 1) for k in SUMS}
    pos = float(d["poss" + sfx].sum())
    m["reb"] = round(m["oreb"] + m["dreb"], 1)
    m["fg_pct"] = round(100 * d["fgm" + sfx].sum() / max(d["fga" + sfx].sum(), 1), 1)
    m["fg3_pct"] = round(100 * d["fg3m" + sfx].sum() / max(d["fg3a" + sfx].sum(), 1), 1)
    m["ft_pct"] = round(100 * d["ftm" + sfx].sum() / max(d["fta" + sfx].sum(), 1), 1)
    m["ortg"] = round(100 * float(d["pts" + sfx].sum()) / pos, 1) if pos else None
    return m


def build_teams(p, tt):
    t, p = team_games(p, tt)
    n = t.groupby("team_id").size(); ok = n[n >= MIN_TEAM_G].index
    tier = dict(zip(tt.team_id, tt.tier)); name = dict(zip(tt.team_id, tt.team)); conf = dict(zip(tt.team_id, tt.conference))
    teams = {}
    for tid, d in t[t.team_id.isin(ok)].groupby("team_id"):
        r = {"id": int(tid), "team": name[tid], "tier": tier[tid], "conf": conf[tid], "g": int(len(d)), "w": int(d.win.sum()), "l": int(len(d) - d.win.sum()),
             "opp_tiers": {k: int(v) for k, v in pd.Series([tier.get(o, "non-D1") for o in d.opp_id]).value_counts().items()},
             "pace": round(float(((d.poss + d.poss_o) / 2).mean()), 1)}
        for w, k in WINDOWS.items():
            x = d if k is None else d.tail(k)
            r[w] = {"g": int(len(x)), "for": side(x, ""), "allowed": side(x, "_o")}
        teams[int(tid)] = r
    keys = ["pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf", "fg_pct", "fg3_pct", "ft_pct", "ortg"]
    for w in WINDOWS:
        for s in keys:
            for sd, rk in (("for", "rk_for"), ("allowed", "rk_al")):
                v = pd.Series({tid: r[w][sd].get(s) for tid, r in teams.items()}, dtype=float)
                hi = (s not in LOWER_BETTER_FOR) if sd == "for" else (s in LOWER_BETTER_FOR)
                if s == "ortg" and sd == "allowed": hi = False
                rank = v.rank(ascending=not hi, method="min")
                for tid, r in teams.items(): r[w].setdefault(rk, {})[s] = int(rank[tid])
    lg = {w: {sd: side(t[t.team_id.isin(ok)] if WINDOWS[w] is None else t[t.team_id.isin(ok)].groupby("team_id").tail(WINDOWS[w]), "" if sd == "for" else "_o") for sd in ("for", "allowed")} for w in WINDOWS}
    units(p, t, teams, ok)
    vs = vs_position(p, tt, ok)
    for tid, r in teams.items(): r["vspos"] = vs["rows"].get(int(tid), {})
    return {"asof": str(t.date.max()), "min_games": MIN_TEAM_G, "windows": list(WINDOWS), "teams": [teams[k] for k in sorted(teams, key=lambda k: teams[k]["team"])], "league": lg, "vspos_rel": vs["rel"]}


def units(p, t, teams, ok, K=150.0):
    """fantasy points per 40 minutes from each team's guards / forwards / centers, ranked in thirds; units seen for few minutes are pulled toward the league rate before ranking."""
    x = p[p.team_id.isin(ok)].copy(); x["pos"] = x.pos.map(POS).fillna("F")
    x["fp"] = x.pts + 1.2 * x.reb + 1.5 * x.ast + 3 * x.stl + 3 * x.blk - x.tov
    for w, k in WINDOWS.items():
        keep = t[["team_id", "event", "date"]].drop_duplicates()
        if k is not None: keep = keep.sort_values("date").groupby("team_id").tail(k)
        d = x.merge(keep[["team_id", "event"]], on=["team_id", "event"])
        agg = d.groupby(["team_id", "pos"])[["min", "fp", "pts", "reb", "ast"]].sum()
        lgp = agg.groupby("pos")[["min", "fp"]].sum(); games = keep.groupby("team_id").size()
        for (tid, pos), r in agg.iterrows():
            if tid not in teams or r["min"] <= 0: continue
            u = teams[int(tid)].setdefault("units", {}).setdefault(w, {})
            u[pos] = {"mpg": round(float(r["min"] / games[tid]), 1), "fp40": round(float(r["fp"] / r["min"] * 40), 1), "pts40": round(float(r["pts"] / r["min"] * 40), 1),
                      "reb40": round(float(r["reb"] / r["min"] * 40), 1), "ast40": round(float(r["ast"] / r["min"] * 40), 1),
                      "s": float((r["fp"] + K * lgp.loc[pos, "fp"] / lgp.loc[pos, "min"]) / (r["min"] + K) * 40)}
        for pos in ("G", "F", "C"):
            v = pd.Series({tid: r["units"][w][pos]["s"] for tid, r in teams.items() if w in r.get("units", {}) and pos in r["units"][w]})
            rk = v.rank(ascending=False, method="min")
            for tid in v.index:
                u = teams[tid]["units"][w][pos]; u["rank"] = int(rk[tid]); u["of"] = int(len(v)); u.pop("s", None)
                u["tier"] = "Top third" if rk[tid] <= len(v) / 3 else "Bottom third" if rk[tid] > 2 * len(v) / 3 else "Middle third"


def vs_position(p, tt, ok, k_min=600.0):
    """per-minute stats each defence allows to guards / forwards / centers vs the league at that position, shrunk toward 0 by minutes seen; reliability = odd vs even games correlation across teams."""
    x = p.copy(); x["pos"] = x.pos.map(POS).fillna("F"); x["reb"] = x.oreb + x.dreb
    t = x.groupby(["event", "team_id"]).size().reset_index()[["event", "team_id"]]
    opp = t.merge(t, on="event"); opp = opp[opp.team_id_x != opp.team_id_y].rename(columns={"team_id_x": "team_id", "team_id_y": "opp_id"})
    x = x.merge(opp, on=["event", "team_id"]); x = x[x.opp_id.isin(ok)]
    x = x[x["min"] > 0]

    def ratios(d):
        tp = d.groupby(["opp_id", "pos"])[VS_STATS + ["min"]].sum(); lp = d.groupby("pos")[VS_STATS + ["min"]].sum(); out = {}
        for (tid, pos), r in tp.iterrows():
            sh = r["min"] / (r["min"] + k_min)
            for s in VS_STATS: out[(tid, pos, s)] = ((r[s] / r["min"]) / (lp.loc[pos, s] / lp.loc[pos, "min"]) - 1, sh) if r["min"] > 0 else (0, 0)
        return out
    full = ratios(x); rows = {}
    for (tid, pos, s), (v, sh) in full.items(): rows.setdefault(int(tid), {})[f"{pos}_{s}"] = round(v * sh * 100, 1)
    days = {e: i for i, e in enumerate(sorted(x.event.unique()))}; half = x.event.map(days) % 2
    a, b = ratios(x[half == 0]), ratios(x[half == 1]); rel = {}
    for pos in ("G", "F", "C"):
        for s in VS_STATS:
            ks = [k for k in a if k[1] == pos and k[2] == s and k in b]
            if len(ks) > 20:
                va, vb = np.array([a[k][0] for k in ks]), np.array([b[k][0] for k in ks])
                rel[f"{pos}_{s}"] = round(float(np.corrcoef(va, vb)[0, 1]), 2) if va.std() > 0 and vb.std() > 0 else None
    return {"rows": rows, "rel": rel}


# ---- consistency ---------------------------------------------------------------------------------------------------------------------------------
WINDOW, MIN_G, MIN_MIN, SPIKE, DUD = 20, 8, 12, 1.3, 0.7
CSTATS = ["fp", "pts", "reb", "ast"]


def build_consistency(tt):
    ps = []
    for y in (2026, 2027):
        f = os.path.join(RAW, f"players_{y}.csv.gz")
        if os.path.exists(f): ps.append(pd.read_csv(f, dtype={"pid": str}))
    g = pd.concat(ps); g = g[g["min"] >= MIN_MIN].copy()
    g["reb"] = g.oreb + g.dreb; g["fp"] = g.pts + 1.2 * g.reb + 1.5 * g.ast + 3 * g.stl + 3 * g.blk - g.tov
    g = g.sort_values(["pid", "date"])
    cur = set(pd.read_csv(os.path.join(RAW, "players_2027.csv.gz"), dtype={"pid": str}).pid)
    last = g.groupby("pid").tail(WINDOW); n = last.groupby("pid").size()
    name = dict(zip(tt.team_id, tt.team)); P = {}
    for pid, x in last[last.pid.isin(n[n >= MIN_G].index) & last.pid.isin(cur)].groupby("pid"):
        d = {"name": x["name"].iloc[-1], "team": name.get(int(x.team_id.iloc[-1]), ""), "n": int(len(x)), "last": [round(float(v), 1) for v in x["fp"].tail(10)]}
        for s in CSTATS:
            v = x[s].astype(float).values; m = float(v.mean()); sd = float(v.std(ddof=1)) if len(v) > 1 else 0.0; med = float(np.median(v))
            e = {"mean": round(m, 1), "median": round(med, 1), "cv": round(sd / m, 3) if m > 0 else None, "floor": round(float(np.percentile(v, 10)), 1), "ceil": round(float(np.percentile(v, 90)), 1)}
            if s in ("fp", "pts") and med > 0: e["spike"] = round(float((v >= SPIKE * med).mean()), 2); e["dud"] = round(float((v <= DUD * med).mean()), 2)
            d[s] = e
        P[pid] = d
    for s in CSTATS:
        ok = [(pid, p[s]) for pid, p in P.items() if p[s]["cv"] is not None and p[s]["mean"] > 0]
        if len(ok) < 30: continue
        means = pd.Series({pid: v["mean"] for pid, v in ok}); band = pd.qcut(means.rank(method="first"), 3, labels=False)
        med = {b: float(np.median([v["cv"] for pid, v in ok if band[pid] == b])) for b in (0, 1, 2)}
        adj = {pid: v["cv"] / med[band[pid]] for pid, v in ok}; a = pd.Series(adj); lo, hi = a.quantile(1 / 3), a.quantile(2 / 3)
        for pid, v in ok:
            v["adj"] = round(adj[pid], 2); v["tag"] = "Steady" if adj[pid] <= lo else "Volatile" if adj[pid] >= hi else "Average"
            if v["tag"] == "Volatile" and "spike" in v: v["shape"] = "Spiky" if v["spike"] - v["dud"] >= 0.10 else "Dud-prone" if v["dud"] - v["spike"] >= 0.10 else "Boom/bust"
    rows = []
    for pid, d in g.groupby("pid"):
        x = d.fp.tail(24).values
        if len(x) == 24 and x.mean() > 0:
            cv = lambda v: v.std(ddof=1) / v.mean(); rows.append((cv(x[0::2]), cv(x[1::2]), cv(x[:12]), cv(x[12:])))
    rel = {}
    if len(rows) > 20:
        r = np.array(rows); rel = {"odd_even": round(float(np.corrcoef(r[:, 0], r[:, 1])[0, 1]), 2), "earlier_later": round(float(np.corrcoef(r[:, 2], r[:, 3])[0, 1]), 2), "players": len(r)}
    return {"window": WINDOW, "min_games": MIN_G, "min_minutes": MIN_MIN, "players": P, "rel": rel}


def main():
    os.makedirs(OUT, exist_ok=True)
    p, tt = load()
    T = build_teams(p, tt)
    json.dump(T, open(os.path.join(OUT, "teams.json"), "w"), separators=(",", ":"), allow_nan=False)
    C = build_consistency(tt)
    json.dump(C, open(os.path.join(OUT, "consistency.json"), "w"), separators=(",", ":"), allow_nan=False)
    tags = pd.Series([v["fp"].get("tag") for v in C["players"].values()]).value_counts().to_dict()
    print(f"teams_site: {len(T['teams'])} teams through {T['asof']}; consistency {len(C['players'])} players {tags}, reliability {C['rel']}")


if __name__ == "__main__":
    main()
