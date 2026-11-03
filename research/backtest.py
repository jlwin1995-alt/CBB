"""Walk-forward college-basketball backtest v0: minutes x shrunk per-minute rates x opponent / pace, scored by cohort.
   python backtest.py <season> [step_days]   needs players_<season>.csv.gz and games_<season>.csv for that season and the two before it (priors)."""
import sys, os, numpy as np, pandas as pd
from scipy import sparse
from scipy.sparse.linalg import lsqr
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D=os.path.join(ROOT,"data","raw"); OUT=os.path.join(ROOT,"research","out"); os.makedirs(OUT,exist_ok=True)
SEASON=int(sys.argv[1]); STEP=int(sys.argv[2]) if len(sys.argv)>2 else 3; RANKMODE=len(sys.argv)>3 and sys.argv[3]=="rank"
if RANKMODE:
    sys.path.insert(0,os.path.join(ROOT,"pipeline")); import recruits as RC; TAB,_,CUR=RC.learn(SEASON)
    if TAB is None: sys.exit("no earlier classes to learn from")
STATS=["pts","reb","ast","stl","blk","tov","fg3m"]; W={"pts":1,"reb":1.2,"ast":1.5,"stl":3,"blk":3,"tov":-1}
def load(y):
    p=pd.read_csv(f"{D}/players_{y}.csv.gz",dtype={"pid":str,"team_id":str,"event":str}); g=pd.read_csv(f"{D}/games_{y}.csv",dtype={"home_id":str,"away_id":str,"event":str}); p["season"]=y; g["season"]=y; return p,g
P=[];G=[]
for y in (SEASON-2,SEASON-1,SEASON):
    if os.path.exists(f"{D}/players_{y}.csv.gz"):
        p,g=load(y); P.append(p); G.append(g)
P=pd.concat(P,ignore_index=True); G=pd.concat(G,ignore_index=True)
for c in ["min","pts","reb","ast","stl","blk","tov","fgm","fga","fg3m","fg3a","ftm","fta","pf","oreb","dreb"]: P[c]=pd.to_numeric(P[c],errors="coerce")
P=P.dropna(subset=["min"]); P=P[P["min"]>0]; P["date"]=pd.to_datetime(P["date"]); G["date"]=pd.to_datetime(G["date"])
G=G.drop_duplicates("event"); P=P.drop_duplicates(["event","pid"])
# opponent per player row
home=G.set_index("event")[["home_id","away_id"]]; P=P.join(home,on="event"); P["opp_id"]=np.where(P.team_id==P.home_id,P.away_id,P.home_id); P["is_home"]=(P.team_id==P.home_id).astype(int)
# D1 filter: both teams must appear in >= 8 games this/last season (drops one-off non-D1 opponents)
cnt=pd.concat([G.home_id,G.away_id]).value_counts(); d1=set(cnt[cnt>=8].index)
G=G[G.home_id.isin(d1)&G.away_id.isin(d1)]; P=P[P.event.isin(set(G.event))]
# team-game totals -> possessions and ratings inputs
T=P.groupby(["event","team_id"]).agg(pts=("pts","sum"),fga=("fga","sum"),oreb=("oreb","sum"),tov=("tov","sum"),fta=("fta","sum")).reset_index()
T["poss"]=T.fga-T.oreb+T.tov+0.475*T.fta
G=G.merge(T.rename(columns={c:"h_"+c for c in T.columns if c not in("event",)}),left_on=["event","home_id"],right_on=["event","h_team_id"],how="left").merge(T.rename(columns={c:"a_"+c for c in T.columns if c not in("event",)}),left_on=["event","away_id"],right_on=["event","a_team_id"],how="left")
G=G.dropna(subset=["h_poss","a_poss"]); G["poss"]=(G.h_poss+G.a_poss)/2
def ratings(upto,lam=60.0):
    """ridge: points per 100 poss = mu + off[team] - def[opp] + hca*home (+ a prior pull from last season's games at weight 0.4)"""
    g=G[(G.date<upto)&(G.season>=SEASON-1)].copy(); w=np.where(g.season==SEASON,1.0,0.4)
    teams=sorted(set(g.home_id)|set(g.away_id)); ix={t:i for i,t in enumerate(teams)}; n=len(teams); m=len(g)
    rows=[];cols=[];vals=[];y=[];ww=[]
    r=0
    for hid,aid,hp,ap,poss,neu,wt in zip(g.home_id,g.away_id,g.h_pts,g.a_pts,g.poss,g.neutral,w):
        for off,de,pts,hm in ((hid,aid,hp,1),(aid,hid,ap,0)):
            rows+= [r,r,r]; cols+=[ix[off],n+ix[de],2*n]; vals+=[1,-1,(hm if not neu else 0)]; y.append(100*pts/poss); ww.append(wt); r+=1
    A=sparse.csr_matrix((vals,(rows,cols)),shape=(r,2*n+1)); yv=np.array(y); mu=yv.mean(); ww=np.sqrt(np.array(ww))
    Aw=sparse.diags(ww)@A; yw=ww*(yv-mu)
    sol=lsqr(Aw,yw,damp=np.sqrt(lam),atol=1e-6,btol=1e-6)[0]
    off={t:sol[ix[t]] for t in teams}; de={t:sol[n+ix[t]] for t in teams}
    pace=(pd.concat([g.assign(t=g.home_id)[["t","poss"]],g.assign(t=g.away_id)[["t","poss"]]]).groupby("t").poss.mean())
    return mu,off,de,pace
POS_TIER={}
def run():
    days=sorted(P[P.season==SEASON].date.unique()); d0=pd.Timestamp(f"{SEASON-1}-11-25"); d1=pd.Timestamp(f"{SEASON}-03-05")
    days=[d for d in days if d0<=d<=d1][::STEP]
    out=[]
    for k,d in enumerate(days):
        H=P[P.date<d]; today=P[P.date==d]
        if today.empty: continue
        mu,off,de,pace=ratings(d); lp=pace.mean()
        cur=H[H.season==SEASON]; prev=H[H.season==SEASON-1]; old=H[H.season==SEASON-2]
        # per-player history aggregates with weights 1.0 / 0.5 / 0.2
        Hh=H.copy(); Hh["w"]=np.select([Hh.season==SEASON,Hh.season==SEASON-1],[1.0,0.5],0.2)
        for s in STATS: Hh[s+"_w"]=Hh[s]*Hh.w
        Hh["min_w"]=Hh["min"]*Hh.w
        agg=Hh.groupby("pid").agg(**{s+"_w":(s+"_w","sum") for s in STATS},min_w=("min_w","sum"),pos=("pos","last"))
        posm=Hh.groupby("pos")[[s+"_w" for s in STATS]+["min_w"]].sum(); prior={s:(posm[s+"_w"]/posm["min_w"]) for s in STATS}
        lg={s:Hh[s+"_w"].sum()/Hh["min_w"].sum() for s in STATS}
        # minutes: recent weighted average this season, prior last season
        c2=cur.sort_values("date"); recent=c2.groupby("pid").tail(6).groupby("pid")["min"].mean(); ncur=c2.groupby("pid").size()
        pm=prev.groupby("pid")["min"].agg(["mean","size"]); pm=pm[pm["size"]>=8]["mean"]
        pg=prev.groupby("pid").size(); allprev=set(prev.pid)|set(old.pid)
        for df in (cur,prev):
            df["fp"]=sum(df[k]*w for k,w in W.items())
        cm=cur.groupby("pid").agg(fp=("fp","mean"),mn=("min","mean")); pmn=prev.groupby("pid").agg(fp=("fp","mean"),mn=("min","mean"))
        newc=0.0
        # newcomer prior: mean minutes of players in their first season with a recorded game (from last season's training)
        first=prev[~prev.pid.isin(set(old.pid))]; newc_min=first.groupby("pid")["min"].mean().mean() if len(first) else 12.0
        for r in today.itertuples():
            n=int(ncur.get(r.pid,0)); pri=pm.get(r.pid,np.nan); bk=None
            if np.isnan(pri): pri=newc_min if r.pid not in allprev else 10.0
            if RANKMODE and r.pid not in allprev:                 # a true newcomer: recruit-rank prior (or the unranked first-year average)
                bk=RC.bucket(CUR[r.pid]) if r.pid in CUR else "unranked"; pri=TAB[bk]["mpg"] if bk in TAB else pri
            rec=recent.get(r.pid,np.nan)
            mproj=(n*(rec if n else 0)+2.0*pri)/(n+2.0) if n else pri
            a=agg.loc[r.pid] if r.pid in agg.index else None
            pos=r.pos if isinstance(r.pos,str) and r.pos in prior["pts"].index else "G"
            mw=0.0 if a is None else a.min_w
            row={"date":d,"season":SEASON,"pid":r.pid,"team":r.team_id,"opp":r.opp_id,"home":r.is_home,"min_a":r.min,"min_p":mproj,"ngames":n,"prev_min":0.0 if r.pid not in set(prev.pid) else prev[prev.pid==r.pid]["min"].sum(),"hist_min":mw,"has_hist":int(r.pid in allprev),"rank":(CUR.get(r.pid) if RANKMODE else np.nan),"bk":bk,"b_fp":(cm.fp.get(r.pid) if r.pid in cm.index else (pmn.fp.get(r.pid) if r.pid in pmn.index else np.nan)),"b_min":(cm.mn.get(r.pid) if r.pid in cm.index else (pmn.mn.get(r.pid) if r.pid in pmn.index else np.nan))}
            o_f=1.0; dfac=1.0
            if r.team_id in off and r.opp_id in de:
                dfac=1.0+0.7*((mu+off[r.team_id]-de[r.opp_id])/mu-(mu+off[r.team_id])/mu) if False else (mu+off[r.team_id]-de[r.opp_id])/(mu+off[r.team_id]) if mu+off[r.team_id]>0 else 1.0
            pf=(pace.get(r.team_id,lp)+pace.get(r.opp_id,lp))/(2*lp)
            for s in STATS:
                k=100.0; pr=prior[s].get(pos,lg[s]); num=0.0 if a is None else a[s+"_w"]
                if bk is not None and bk in TAB: pr=TAB[bk][s]
                rate=(num+k*pr)/(mw+k)
                adj=dfac if s in("pts","fg3m") else 1.0
                row[s+"_p"]=mproj*rate*adj*pf; row[s+"_a"]=getattr(r,s)
            out.append(row)
        if k%10==0: print(SEASON,str(d.date()),len(out),flush=True)
    R=pd.DataFrame(out); R.to_pickle(f"{OUT}/bt_{SEASON}{'_rank' if RANKMODE else ''}.pkl"); return R
if __name__=="__main__": 
    R=run(); print("rows",len(R))
