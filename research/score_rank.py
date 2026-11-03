"""v0 vs recruit-rank prior on the same player-games.  python score_rank.py 2025 2026"""
import sys, os, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D=os.path.join(ROOT,"data","raw"); OUT=os.path.join(ROOT,"research","out"); os.makedirs(OUT,exist_ok=True); W={"pts":1,"reb":1.2,"ast":1.5,"stl":3,"blk":3,"tov":-1}
A=[]
for y in map(int,sys.argv[1:]):
    b=pd.read_pickle(f"{OUT}/bt_{y}.pkl"); r=pd.read_pickle(f"{OUT}/bt_{y}_rank.pkl")
    k=["date","pid","team"]; m=b.merge(r[k+["min_p","bk","rank"]+[s+"_p" for s in W]],on=k,suffixes=("","_r")); A.append(m)
M=pd.concat(A,ignore_index=True)
M["fp_a"]=sum(M[s+"_a"]*w for s,w in W.items()); M["fp_v0"]=sum(M[s+"_p"]*w for s,w in W.items()); M["fp_r"]=sum(M[s+"_p_r"]*w for s,w in W.items())
M=M[(M.min_p>=12)|(M.min_p_r>=12)]               # projected rotation by either version
N=M[M.has_hist==0].copy()                        # true newcomers (no earlier D1 games)
N["grp"]=np.where(N.bk.isin(["1-10","11-25"]),"recruit 1-25",np.where(N.bk.isin(["26-50","51-75"]),"recruit 26-75",np.where(N.bk.isin(["76-100","101-150"]),"recruit 76-150","unranked newcomer")))
N["gb"]=pd.cut(N.ngames,[-1,2,5,10,20,100],labels=["0-2","3-5","6-10","11-20","21+"])
def rep(x,lab):
    if len(x)<30: return
    print(f"{lab:36s} n={len(x):5d} | minutes MAE v0 {(x.min_p-x.min_a).abs().mean():5.2f} rank {(x.min_p_r-x.min_a).abs().mean():5.2f} naive {(x.b_min-x.min_a).abs().mean():5.2f} | FP MAE v0 {(x.fp_v0-x.fp_a).abs().mean():5.2f} rank {(x.fp_r-x.fp_a).abs().mean():5.2f} naive {(x.b_fp-x.fp_a).abs().mean():5.2f} | bias min v0 {(x.min_p-x.min_a).mean():+5.2f} rank {(x.min_p_r-x.min_a).mean():+5.2f}")
print("seasons",sorted(M.season.unique()),"newcomer player-games",len(N))
rep(N,"ALL newcomers")
for g,x in N.groupby("grp"): rep(x,g)
print()
for (g,b),x in N.groupby(["grp","gb"],observed=True): rep(x,f"{g} | games {b}")
print(); rep(M,"EVERYONE (all cohorts)")
