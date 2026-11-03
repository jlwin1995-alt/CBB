"""v1: recruit-rank prior + newcomer cutoff + 200-minute team budget (with and without known absences).  python score2.py 2025 2026"""
import sys, os, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D=os.path.join(ROOT,"data","raw"); OUT=os.path.join(ROOT,"research","out"); os.makedirs(OUT,exist_ok=True); W={"pts":1,"reb":1.2,"ast":1.5,"stl":3,"blk":3,"tov":-1}
R=pd.concat([pd.read_pickle(f"{OUT}/bt2_{y}.pkl") for y in map(int,sys.argv[1:])],ignore_index=True)
R["fp_a"]=sum(R[s+"_a"]*w for s,w in W.items())
V={"rank prior only":"min_p","budget, absences unknown 50%":"min_nor50","budget, absences unknown 100%":"min_nor100","budget, absences KNOWN 50%":"min_or50","budget, absences KNOWN 100%":"min_or100"}
R=R[R.min_p>=12].copy()
def rep(x,lab,cut=None):
    if cut is not None: x=x[cut(x)]
    if len(x)<50: return
    parts=[]
    for k,c in V.items():
        e=(x[c]-x.min_a); f=(x[c]*x.fpm-x.fp_a); parts.append(f"{k.split(',')[0][:6]}{k.split(',')[-1][-8:]} min {e.abs().mean():4.2f}/{e.mean():+.2f} fp {f.abs().mean():4.2f}")
    print(f"{lab:30s} n={len(x):5d} | "+" | ".join(parts))
print("columns: minutes MAE/bias, FP MAE   [variants: rank-only, unknown 50%, unknown 100%, known 50%, known 100%]")
rep(R,"EVERYONE")
rep(R,"returners",lambda x:x.has_hist==1)
rep(R,"newcomers (all)",lambda x:x.has_hist==0)
cut=lambda x:~((x.has_hist==0)&(x.bk=="unranked")&(x.ngames<3))
print("\\nnewcomer cutoff: drop unranked newcomers with <3 games"); rep(R,"EVERYONE (after cutoff)",cut); rep(R,"newcomers (after cutoff)",lambda x:(x.has_hist==0)&cut(x))
for b,x in R[cut(R)].groupby(pd.cut(R[cut(R)].ngames,[-1,2,5,10,20,100],labels=["0-2","3-5","6-10","11-20","21+"]),observed=True): rep(x,f"games {b}")
R["adj"]=R.min_or100/R.min_nor100-1
print("\\nteam-days where the oracle budget moved this player's minutes by >5% (a rotation man out)")
rep(R,"known-absence beneficiaries",lambda x:x.adj>0.05); rep(R,"known-absence, others",lambda x:x.adj<=0.05)
