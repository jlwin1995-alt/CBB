"""Retro check of the model against the lines already graded: project each game from history strictly before its date (roster = players who actually played, so
availability is known, a mild leak versus the live pipeline), then see how often the side the projection favours beat the closing line.
   python research/retro_lines.py"""
import os, sys, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import model as M, recruits as RC, grade_lines as GL, project as PJ
season = 2027
P, G = PJ.load_history(season); tab, _, cur = RC.learn(season)
g = pd.read_csv(os.path.join(ROOT, "data/log/lines_graded.csv"), dtype={"espn_event": str}); g = g[g.result.isin(["over", "under"])]
box = GL.load_boxes(); box["event"] = box["event"].astype(str)
home = G.set_index("event")[["home_id", "away_id"]]
res = []
for ev, gg in g.groupby("espn_event"):
    d = box[box.event == ev]
    if d.empty or ev not in home.index: continue
    day = pd.Timestamp(d.date.iloc[0])
    t = d.join(home, on="event"); t = t.assign(opp_id=np.where(t.team_id.astype(str) == t.home_id, t.away_id, t.home_id), is_home=(t.team_id.astype(str) == t.home_id).astype(int), team_id=t.team_id.astype(str), pid=t.pid.astype(str))
    pr = M.project(P, G, t[["event", "team_id", "opp_id", "is_home", "pid", "pos"]], season, day, tab, cur)
    pr = pr.set_index("pid")
    for r in gg.itertuples():
        b = t[t.name.map(GL.nz) == GL.nz(r.player)]
        if len(b) != 1: continue
        pid = b.pid.iloc[0]
        if pid not in pr.index: continue
        st = GL.MARKET_STAT[r.market]; pv = pr.loc[pid, st + "_p"]
        if pv != pv: continue
        res.append(dict(market=r.market, book=r.book, point=r.point, proj=pv, actual=r.actual, result=r.result, avg=r.avg_prior))
R = pd.DataFrame(res); R["pick"] = np.where(R.proj > R.point, "over", "under"); R["hit"] = R.pick == R.result; R["rel"] = (R.proj - R.point).abs() / R.point.clip(lower=.5)
print("lines with a projection", len(R), "of", len(g)); print("pick hit rate %.3f" % R.hit.mean(), " picks over:", (R.pick == "over").sum())
print(R.groupby("market").hit.agg(["sum", "size"]).to_string())
for lo, hi in ((0, .1), (.1, .2), (.2, 9)): s = R[(R.rel >= lo) & (R.rel < hi)]; print(f"edge {lo:.0%}-{hi:.0%}: {s.hit.sum()}/{len(s)}")
print("mean(proj - line) %.2f, mean(actual - line) %.2f, mean(actual - proj) %.2f" % ((R.proj - R.point).mean(), (R.actual - R.point).mean(), (R.actual - R.proj).mean()))
R.to_csv(os.path.join(ROOT, "research/out/retro_lines.csv"), index=False)
