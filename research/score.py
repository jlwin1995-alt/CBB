"""Score the CBB walk-forward backtest by cohort.  python score.py 2024 2025 2026"""
import sys, os, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D=os.path.join(ROOT,"data","raw"); OUT=os.path.join(ROOT,"research","out"); os.makedirs(OUT,exist_ok=True); W={"pts":1,"reb":1.2,"ast":1.5,"stl":3,"blk":3,"tov":-1}
R=pd.concat([pd.read_pickle(f"{OUT}/bt_{y}.pkl") for y in map(int,sys.argv[1:]) if os.path.exists(f"{OUT}/bt_{y}.pkl")],ignore_index=True)
R["fp_p"]=sum(R[k+"_p"]*w for k,w in W.items()); R["fp_a"]=sum(R[k+"_a"]*w for k,w in W.items())
R=R[R.min_p>=12].copy()          # projected rotation players, as in the NBA scoring
def cohort(r):
    if not r.has_hist: return "newcomer (no D1 history)"
    if r.prev_min<150 and r.ngames<5: return "low-minute returner"
    return "returner"
R["cohort"]=R.apply(cohort,axis=1)
R["gb"]=pd.cut(R.ngames,[-1,2,5,10,20,100],labels=["0-2","3-5","6-10","11-20","21+"])
def rep(x,lab):
    if len(x)<40 or x.b_fp.notna().sum()<40: return
    nb=int(x.b_fp.isna().sum()); y=x[x.b_fp.notna()]      # compare with the naive average only where the naive average exists
    e=(y.fp_p-y.fp_a); eb=(y.b_fp-y.fp_a); em=(y.min_p-y.min_a); emb=(y.b_min-y.min_a)
    print(f"{lab:34s} n={len(y):5d} (+{nb:4d} no naive) min MAE {em.abs().mean():5.2f} (naive {emb.abs().mean():5.2f}) bias {em.mean():+5.2f} | FP MAE {e.abs().mean():5.2f} (naive {eb.abs().mean():5.2f}) bias {e.mean():+5.2f}")
print("rows",len(R),"seasons",sorted(R.season.unique())); rep(R,"ALL (projected 12+ min)")
for c,g in R.groupby("cohort"): rep(g,c)
print(); 
for b,g in R.groupby("gb",observed=True): rep(g,f"games played this season {b}")
print()
for (c,b),g in R.groupby(["cohort","gb"],observed=True): rep(g,f"{c} | {b}")
