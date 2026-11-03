"""Backfill ESPN men's college basketball box scores (Division I scoreboard group 50) one season at a time, resumable.
   python fetch_cbb.py 2024 2025 2026      (season = ending year; each runs Nov 1 .. Apr 10)"""
import sys, os, json, time, datetime as dt, csv, gzip, threading
import requests
from concurrent.futures import ThreadPoolExecutor
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D=os.path.join(ROOT,"data","raw"); OUT=os.path.join(ROOT,"research","out"); os.makedirs(OUT,exist_ok=True)
B="https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
S=requests.Session(); S.headers["User-Agent"]="bball-cbb-backfill"
lock=threading.Lock()
def get(url,params,tries=4):
    for t in range(tries):
        try:
            r=S.get(url,params=params,timeout=40)
            if r.status_code==200: return r.json()
        except Exception: pass
        time.sleep(1.5*(t+1))
    return None
KEYS=["minutes","points","fg","fg3","ft","rebounds","assists","turnovers","steals","blocks","oreb","dreb","fouls"]
def pm(x):
    try: a,b=str(x).split("-"); return int(a),int(b)
    except Exception: return None,None
def one(ev):
    j=get(B+"/summary",{"event":ev["id"]})
    if not j: return ev["id"],None,None
    rows=[]; teams={}
    for t in j.get("boxscore",{}).get("players",[]):
        tid=str(t["team"]["id"]); teams[tid]=t["team"].get("displayName")
        for st in t.get("statistics",[]):
            ks=st.get("keys",[]); ix={k:i for i,k in enumerate(ks)}
            for a in st.get("athletes",[]):
                if a.get("didNotPlay") or not a.get("stats"): continue
                v=a["stats"]
                def g(k): return v[ix[k]] if k in ix else None
                fgm,fga=pm(g("fieldGoalsMade-fieldGoalsAttempted")); tm,ta=pm(g("threePointFieldGoalsMade-threePointFieldGoalsAttempted")); fm,fa=pm(g("freeThrowsMade-freeThrowsAttempted"))
                try: mn=float(g("minutes"))
                except Exception: continue
                rows.append([ev["id"],ev["date"][:10],tid,str(a["athlete"]["id"]),a["athlete"].get("displayName"),int(bool(a.get("starter"))),(a["athlete"].get("position") or {}).get("abbreviation"),mn,
                    g("points"),g("rebounds"),g("assists"),g("steals"),g("blocks"),g("turnovers"),fgm,fga,tm,ta,fm,fa,g("fouls"),g("offensiveRebounds"),g("defensiveRebounds")])
    return ev["id"],rows,teams
PH=["event","date","team_id","pid","name","starter","pos","min","pts","reb","ast","stl","blk","tov","fgm","fga","fg3m","fg3a","ftm","fta","pf","oreb","dreb"]
GH=["event","date","season","home_id","home","home_score","away_id","away","away_score","neutral","conf_game"]
def season(y):
    pf=f"{D}/players_{y}.csv.gz"; gf=f"{D}/games_{y}.csv"; dn=f"{D}/done_{y}.json"
    done=set(json.load(open(dn))) if os.path.exists(dn) else set()
    if not os.path.exists(pf): 
        with gzip.open(pf,"wt",newline="") as f: csv.writer(f).writerow(PH)
        with open(gf,"w",newline="") as f: csv.writer(f).writerow(GH)
    d0=dt.date(y-1,11,1); d1=dt.date(y,4,10); day=d0
    while day<=d1:
        ds=day.strftime("%Y%m%d")
        if ds in done: day+=dt.timedelta(days=1); continue
        sb=get(B+"/scoreboard",{"dates":ds,"groups":"50","limit":"400"})
        if sb is None: print("scoreboard failed",ds,flush=True); day+=dt.timedelta(days=1); continue
        evs=[e for e in sb.get("events",[]) if e["status"]["type"]["name"]=="STATUS_FINAL"]
        with ThreadPoolExecutor(16) as ex: res=list(ex.map(one,evs))
        okc=0
        with lock:
            with gzip.open(pf,"at",newline="") as f, open(gf,"a",newline="") as g:
                w=csv.writer(f); gw=csv.writer(g)
                for ev,(eid,rows,teams) in zip(evs,res):
                    if not rows: continue
                    c=ev["competitions"][0]; cp={x["homeAway"]:x for x in c["competitors"]}
                    if "home" not in cp or "away" not in cp: continue
                    w.writerows(rows); okc+=1
                    gw.writerow([eid,ev["date"][:10],y,cp["home"]["team"]["id"],cp["home"]["team"].get("displayName"),cp["home"].get("score"),cp["away"]["team"]["id"],cp["away"]["team"].get("displayName"),cp["away"].get("score"),int(bool(c.get("neutralSite"))),int(bool(c.get("conferenceCompetition")))])
        failed=len(evs)-okc
        if failed==0:
            done.add(ds); json.dump(sorted(done),open(dn,"w"))
        print(y,ds,"events",len(evs),"ok",okc,"failed",failed,flush=True)
        day+=dt.timedelta(days=1)
if __name__=="__main__":
    for y in map(int,sys.argv[1:]): season(y)
    print("ALL DONE",flush=True)
