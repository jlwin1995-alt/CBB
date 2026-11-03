"""Recruit-rank priors for true freshmen. Class C plays its first season ending in C+1.
   learn(season): from classes whose first season is BEFORE `season` only (walk-forward), returns bucket tables and the pid->rank map for this season's class."""
import os, re, unicodedata, numpy as np, pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D=os.path.join(ROOT,"data","raw"); OUT=os.path.join(ROOT,"research","out"); os.makedirs(OUT,exist_ok=True); EDGES=[0,10,25,50,75,100,150]; LAB=["1-10","11-25","26-50","51-75","76-100","101-150"]
STATS=["pts","reb","ast","stl","blk","tov","fg3m"]
def norm(n):
    n=unicodedata.normalize("NFKD",str(n)).encode("ascii","ignore").decode().lower(); n=re.sub(r"[.'’,-]"," ",n); n=re.sub(r"\b(jr|sr|ii|iii|iv|v)\b","",n); return " ".join(n.split())
def bucket(rank): return LAB[np.searchsorted(EDGES,rank,side="left")-1]
def season_players(y):
    p=pd.read_csv(f"{D}/players_{y}.csv.gz",dtype={"pid":str}); p["key"]=p.name.map(norm); return p
def class_map(c):
    """pid -> rank for recruits of class c found in the box scores of season c+1 (name match; skip ambiguous names)"""
    r=pd.read_csv(f"{D}/recruits/c{c}.csv"); r["key"]=r.Player.map(norm); p=season_players(c+1)
    k=p.groupby("key").pid.nunique(); amb=set(k[k>1].index); g=p.groupby("key").pid.first()
    out={}
    for key,rank in zip(r.key,r.Rank):
        if key in g.index and key not in amb: out[g[key]]=int(rank)
    return out
def learn(season):
    """tables from first seasons < season: bucket -> (mpg, rates dict); and 'unranked' first-year table; plus this season's pid->rank map"""
    tr=[]; 
    for c in (2023,2024,2025):
        if c+1>=season: continue
        p=season_players(c+1); p=p[p["min"]>0]; cm=class_map(c)
        prior=set()
        for y in range(2023,c+1):
            if os.path.exists(f"{D}/players_{y}.csv.gz"): prior|=set(pd.read_csv(f"{D}/players_{y}.csv.gz",dtype={"pid":str}).pid)
        fresh=p[~p.pid.isin(prior)]
        g=fresh.groupby("pid").agg(games=("event","nunique"),**{"min":("min","sum")},**{s:(s,"sum") for s in STATS}).reset_index()
        g["rank"]=g.pid.map(cm); tr.append(g)
    cur=class_map(season-1) if os.path.exists(f"{D}/recruits/c{season-1}.csv") else {}
    if not tr: return None,None,cur
    T=pd.concat(tr); T["bk"]=[bucket(r) if r==r else "unranked" for r in T["rank"]]
    tab={}
    for b,g in T.groupby("bk"):
        tab[b]={"mpg":g["min"].sum()/g.games.sum(),"n":len(g),**{s:g[s].sum()/g["min"].sum() for s in STATS}}
    return tab,T,cur
if __name__=="__main__":
    for s in (2025,2026):
        tab,T,cur=learn(s); print(s,"training freshmen",len(T),"this class matched",len(cur)); 
        for b,v in tab.items(): print("  ",b,round(v["mpg"],1),v["n"],round(v["pts"]*40,1),"pts/40")
