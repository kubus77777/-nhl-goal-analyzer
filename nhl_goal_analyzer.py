import streamlit as st
import requests
import pandas as pd

BASE="https://api-web.nhle.com/v1"
TEAMS={"Anaheim Ducks":"ANA","Boston Bruins":"BOS","Buffalo Sabres":"BUF","Calgary Flames":"CGY","Carolina Hurricanes":"CAR","Chicago Blackhawks":"CHI","Colorado Avalanche":"COL","Columbus Blue Jackets":"CBJ","Dallas Stars":"DAL","Detroit Red Wings":"DET","Edmonton Oilers":"EDM","Florida Panthers":"FLA","Los Angeles Kings":"LAK","Minnesota Wild":"MIN","Montreal Canadiens":"MTL","Nashville Predators":"NSH","New Jersey Devils":"NJD","New York Islanders":"NYI","New York Rangers":"NYR","Ottawa Senators":"OTT","Philadelphia Flyers":"PHI","Pittsburgh Penguins":"PIT","San Jose Sharks":"SJS","Seattle Kraken":"SEA","St. Louis Blues":"STL","Tampa Bay Lightning":"TBL","Toronto Maple Leafs":"TOR","Utah Mammoth":"UTA","Vancouver Canucks":"VAN","Vegas Golden Knights":"VGK","Washington Capitals":"WSH","Winnipeg Jets":"WPG"}
SEASONS={"2024/25":"20242025","2025/26":"20252026","2026/27":"20262027"}

st.set_page_config(page_title="NHL Goal Analyzer",page_icon="🏒",layout="centered")

@st.cache_data(ttl=3600)
def get(url):
    r=requests.get(url,timeout=25); r.raise_for_status(); return r.json()

def nm(x):
    a=x.get("firstName",{}); b=x.get("lastName",{})
    a=a.get("default","") if isinstance(a,dict) else a
    b=b.get("default","") if isinstance(b,dict) else b
    return f"{a} {b}".strip()

@st.cache_data(ttl=86400)
def roster(team,season):
    d=get(f"{BASE}/roster/{team}/{season}"); out=[]
    for k in ("forwards","defensemen","goalies"):
        for p in d.get(k,[]):
            if p.get("id"): out.append({"id":int(p["id"]),"name":nm(p),"pos":p.get("positionCode",""),"team":team})
    return list({p["id"]:p for p in out}.values())

@st.cache_data(ttl=86400)
def log(pid,season):
    return get(f"{BASE}/player/{pid}/game-log/{season}/2")

def games(d):
    out=[]
    for g in d.get("gameLog",d.get("games",[])):
        hr=str(g.get("homeRoad",g.get("homeRoadFlag",""))).upper()
        out.append({"g":int(g.get("goals",g.get("G",0)) or 0),"home":hr in ("H","HOME"),
                    "opp":str(g.get("opponentTeamAbbrev",g.get("opponentAbbrev",g.get("opponent","")))).upper(),
                    "date":str(g.get("gameDate",g.get("date","")))})
    return out

def stt(gs):
    gp=len(gs); gg=sum(x["g"]>=1 for x in gs); p=gg/gp*100 if gp else 0
    return gg,gp,p,100/p if p else 0

@st.cache_data(ttl=3600)
def allgames(pid,seasons):
    a=[]
    for s in seasons:
        try:a+=games(log(pid,s))
        except:pass
    return sorted(a,key=lambda x:x["date"])

def analyse(gs,opp=None):
    if opp: gs=[x for x in gs if x["opp"]==opp]
    h=[x for x in gs if x["home"]]; a=[x for x in gs if not x["home"]]
    return stt(gs),stt(h),stt(a),stt(gs[-5:]),stt(gs[-10:])

def fmt(x): return f"{x[0]}/{x[1]} ({x[2]:.1f}%)"

st.title("🏒 NHL Goal Analyzer")
st.caption("Základ: % zápasů, ve kterých hráč vstřelil alespoň 1 gól.")

mode=st.radio("Režim",["Hráči jednoho týmu","TOP 50 střelců"],horizontal=True)

if mode=="Hráči jednoho týmu":
    tn=st.selectbox("1. Tým",list(TEAMS),index=list(TEAMS).index("Montreal Canadiens"))
    team=TEAMS[tn]
    sl=st.multiselect("2. Sezony",list(SEASONS),default=["2024/25","2025/26"])
    only_f=st.checkbox("Pouze útočníci")
    if not sl: st.stop()
    rs=SEASONS["2026/27"] if "2026/27" in sl else SEASONS["2025/26"]
    try:r=roster(team,rs)
    except:
        r=roster(team,"20252026")
    if only_f:r=[p for p in r if p["pos"] in ("C","L","R","F")]
    sel=st.multiselect("3. Hráči",[p["name"] for p in r],placeholder="Vyber hráče")
    opps=["Všichni soupeři"]+sorted(set(TEAMS.values())-{team})
    oc=st.selectbox("4. Soupeř",opps); opp=None if oc=="Všichni soupeři" else oc
    if sel:
        mp={p["name"]:p for p in r}; rows=[]
        for n in sel:
            gs=allgames(mp[n]["id"],tuple(SEASONS[x] for x in sl)); t,h,a,l5,l10=analyse(gs,opp)
            rows.append({"Hráč":n,"1+ G":t[0],"GP":t[1],"%":round(t[2],1),"Fair":round(t[3],2),
                         "L5":fmt(l5),"L10":fmt(l10),"Doma":fmt(h),"Venku":fmt(a),
                         "Value":f"{((t[2]/100)*odds-1)*100:+.1f}%"})
        st.dataframe(pd.DataFrame(rows).sort_values(["%","1+ G"],ascending=False),hide_index=True,use_container_width=True)
    else: st.info("Vyber hráče.")

else:
    season=st.selectbox("Sezona TOP 50",list(SEASONS),index=1)
    only_f=st.checkbox("Pouze útočníci")
    try:
        d=get(f"{BASE}/skater-stats-leaders/{SEASONS[season]}/2?categories=goals&limit=50")
        items=d if isinstance(d,list) else next((d.get(k,[]) for k in ("goals","leaders","skaterStatsLeaders","data") if isinstance(d.get(k),list)),[])
        rows=[]
        for x in items[:50]:
            pid=x.get("id") or x.get("playerId")
            if not pid: continue
            try:
                land=get(f"{BASE}/player/{pid}/landing")
                pos=land.get("position","")
                if only_f and pos not in ("C","L","R","F"): continue
                name=nm(land) or x.get("name") or x.get("playerName") or str(pid)
            except:
                if only_f: continue
                name=x.get("name") or x.get("playerName") or str(pid)
            gs=games(log(int(pid),SEASONS[season])); s=stt(gs)
            rows.append({"Hráč":name,"Tým":x.get("teamAbbrev",x.get("team","")),"G":x.get("value",x.get("goals",0)),
                         "1+ G":s[0],"GP":s[1],"%":round(s[2],1),"Fair":round(s[3],2)})
        df=pd.DataFrame(rows).sort_values(["1+ G","G"],ascending=False).head(50)
        st.dataframe(df,hide_index=True,use_container_width=True)
    except Exception as e:
        st.error("NHL API momentálně nevrátilo data pro TOP 50.")
        st.caption(str(e))

st.divider()
st.caption("Zdroj: NHL API. Pouze základní část; každý zápas s 1+ gólem se počítá právě jednou.")
