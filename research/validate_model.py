"""Check pipeline/model.py against the backtest: walk-forward over one season, roster = players who actually played that day (so availability is known).
   python research/validate_model.py <season> [step_days]   prints minutes MAE, fantasy-point MAE and the season-to-date-average baseline."""
import sys, os, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D = os.path.join(ROOT, "data", "raw")
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import model as M, recruits as RC
S = int(sys.argv[1]); STEP = int(sys.argv[2]) if len(sys.argv) > 2 else 4
START = sys.argv[3] if len(sys.argv) > 3 else "12-01"; END = sys.argv[4] if len(sys.argv) > 4 else "03-05"; TAG = sys.argv[5] if len(sys.argv) > 5 else ""
bx, gm = [], []
for y in (S - 2, S - 1, S):
    bx.append(pd.read_csv(f"{D}/players_{y}.csv.gz", dtype={"pid": str, "team_id": str, "event": str}).assign(season=y))
    gm.append(pd.read_csv(f"{D}/games_{y}.csv", dtype={"home_id": str, "away_id": str, "event": str}).assign(season=y))
P, G = M.prep(pd.concat(bx, ignore_index=True), pd.concat(gm, ignore_index=True))
TAB, _, CUR = RC.learn(S)
home = G.set_index("event")[["home_id", "away_id"]]
days = sorted(P[P.season == S].date.unique()); d0 = pd.Timestamp(f"{S-1}-{START}"); d1 = pd.Timestamp(f"{S-1}-{END}" if END[:2] in ("11", "12") else f"{S}-{END}")
days = [d for d in days if d0 <= d <= d1][::STEP]
rows = []
for d in days:
    today = P[P.date == d].join(home, on="event")
    if today.empty: continue
    today = today.assign(opp_id=np.where(today.team_id == today.home_id, today.away_id, today.home_id), is_home=(today.team_id == today.home_id).astype(int))
    pr = M.project(P, G, today[["event", "team_id", "opp_id", "is_home", "pid", "pos"]], S, d, TAB, CUR)
    a = today.set_index(["event", "pid"]); pr = pr.join(a[["min", "pts", "reb", "ast", "stl", "blk", "tov", "fg3m"]], on=["event", "pid"], rsuffix="_a")
    pr["date"] = d; rows.append(pr)
R = pd.concat(rows, ignore_index=True)
# season-to-date average baseline for the same rows
H = P[P.season == S].sort_values("date")
def fp(df, suf): return sum(df[k + suf] * w for k, w in M.SCORING.items())
R["fp_p"] = sum(R[k + "_p"] * w for k, w in M.SCORING.items()); R["fp_a"] = sum(R[k] * w for k, w in M.SCORING.items())
base = []
for d, g in R.groupby("date"):
    h = H[H.date < d]; m = h.groupby("pid").apply(lambda x: pd.Series({"b_min": x["min"].mean(), "b_fp": (sum(x[k] * w for k, w in M.SCORING.items())).mean()}))
    base.append(g.join(m, on="pid"))
R = pd.concat(base)
ok = R.dropna(subset=["fp_p", "b_fp"])
print("rows", len(R), "projected", R.fp_p.notna().sum(), "with baseline", len(ok))
print("model   minutes MAE %.2f  FP MAE %.2f  FP bias %.2f" % ((ok.min_p - ok["min"]).abs().mean(), (ok.fp_p - ok.fp_a).abs().mean(), (ok.fp_p - ok.fp_a).mean()))
print("average minutes MAE %.2f  FP MAE %.2f  FP bias %.2f" % ((ok.b_min - ok["min"]).abs().mean(), (ok.b_fp - ok.fp_a).abs().mean(), (ok.b_fp - ok.fp_a).mean()))
for c, g in ok.groupby(ok.newcomer.map({0: "returner", 1: "newcomer"})): print(c, len(g), "model FP MAE %.2f vs average %.2f" % ((g.fp_p - g.fp_a).abs().mean(), (g.b_fp - g.fp_a).abs().mean()))
nn = R[R.fp_p.isna()]; print("not projected (unranked newcomers under 3 games):", len(nn))
R.to_pickle(os.path.join(ROOT, "research", "out", f"validate_{S}{TAG}.pkl")) if os.path.isdir(os.path.join(ROOT, "research", "out")) else None
