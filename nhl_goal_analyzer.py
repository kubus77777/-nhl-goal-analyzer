import streamlit as st
import requests
import pandas as pd

BASE = "https://api-web.nhle.com/v1"

TEAM_IDS = {
    "Anaheim Ducks":"ANA","Boston Bruins":"BOS","Buffalo Sabres":"BUF",
    "Calgary Flames":"CGY","Carolina Hurricanes":"CAR","Chicago Blackhawks":"CHI",
    "Colorado Avalanche":"COL","Columbus Blue Jackets":"CBJ","Dallas Stars":"DAL",
    "Detroit Red Wings":"DET","Edmonton Oilers":"EDM","Florida Panthers":"FLA",
    "Los Angeles Kings":"LAK","Minnesota Wild":"MIN","Montreal Canadiens":"MTL",
    "Nashville Predators":"NSH","New Jersey Devils":"NJD","New York Islanders":"NYI",
    "New York Rangers":"NYR","Ottawa Senators":"OTT","Philadelphia Flyers":"PHI",
    "Pittsburgh Penguins":"PIT","San Jose Sharks":"SJS","Seattle Kraken":"SEA",
    "St. Louis Blues":"STL","Tampa Bay Lightning":"TBL","Toronto Maple Leafs":"TOR",
    "Utah Mammoth":"UTA","Vancouver Canucks":"VAN","Vegas Golden Knights":"VGK",
    "Washington Capitals":"WSH","Winnipeg Jets":"WPG"
}
SEASONS = {"2025/26":"20252026","2024/25":"20242025"}

@st.cache_data(ttl=3600)
def get_json(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=86400)
def team_roster(team):
    data = get_json(f"{BASE}/roster/{team}/20252026")
    players = []
    for key in ("forwards","defensemen","goalies"):
        for p in data.get(key, []):
            pid = p.get("id")
            first, last = p.get("firstName",{}), p.get("lastName",{})
            if isinstance(first,dict): first = first.get("default","")
            if isinstance(last,dict): last = last.get("default","")
            if pid:
                players.append({"id":int(pid),"name":f"{first} {last}".strip(),
                                 "position":p.get("positionCode","")})
    return players

@st.cache_data(ttl=86400)
def player_log(player_id, season):
    return get_json(f"{BASE}/player/{player_id}/game-log/{season}/2")

def games_from(data):
    games = data.get("gameLog", data.get("games", []))
    result = []
    for g in games:
        goals = int(g.get("goals", g.get("G", 0)) or 0)
        hr = str(g.get("homeRoad", g.get("homeRoadFlag",""))).upper()
        opponent = (
            g.get("opponentTeamAbbrev")
            or g.get("opponentAbbrev")
            or g.get("opponent")
            or ""
        )
        date = g.get("gameDate") or g.get("date") or ""
        result.append({
            "goals": goals,
            "home": hr in ("H","HOME"),
            "opponent": str(opponent).upper(),
            "date": str(date)
        })
    return result

def stats(games):
    gp=len(games)
    gg=sum(x["goals"]>=1 for x in games)
    pct=gg/gp*100 if gp else 0
    return gg,gp,pct,(100/pct if pct else 0)

def analyze(pid, seasons, opponent=None):
    games=[]
    for s in seasons:
        try:
            games += games_from(player_log(pid,s))
        except Exception:
            pass

    games = sorted(games, key=lambda x: x["date"])
    if opponent:
        games = [g for g in games if g["opponent"] == opponent]

    home=[g for g in games if g["home"]]
    away=[g for g in games if not g["home"]]

    def recent(n):
        return stats(games[-n:]) if games else (0,0,0,0)

    return stats(games),stats(home),stats(away),recent(5),recent(10),recent(20)

st.set_page_config(page_title="NHL Goal Analyzer",page_icon="🏒",layout="centered")
st.title("🏒 NHL Goal Analyzer")
st.caption("Vyber tým, hráče, soupeře a případně kurz. Data se načítají přímo z NHL API.")

teams=list(TEAM_IDS)
team_options=["Všechny týmy"] + teams
team_name=st.selectbox("1. Tým",team_options,index=team_options.index("Montreal Canadiens"))

if team_name == "Všechny týmy":
    selected_team_codes = list(TEAM_IDS.values())
    roster = []
    for code in selected_team_codes:
        try:
            roster.extend(team_roster(code))
        except Exception:
            pass
else:
    selected_team_codes = [TEAM_IDS[team_name]]
    roster = team_roster(selected_team_codes[0])

# Odstranění případných duplicit hráčů
unique = {p["id"]: p for p in roster}
roster = list(unique.values())
names=[p["name"] for p in roster]

selected_seasons=st.multiselect(
    "2. Sezony",list(SEASONS),
    default=["2025/26","2024/25"]
)

opponents = ["Všichni soupeři"] + sorted(
    set(TEAM_IDS.values()) - set(selected_team_codes)
)
opponent_choice = st.selectbox("3. Soupeř", opponents)
opponent = None if opponent_choice == "Všichni soupeři" else opponent_choice

selected=st.multiselect(
    "4. Hráči",
    names,
    placeholder="Vyber jednoho nebo více hráčů"
)

odds = st.number_input(
    "Kurz na gól (volitelné)",
    min_value=1.01,
    max_value=100.0,
    value=2.00,
    step=0.05
)

if not selected_seasons:
    st.warning("Vyber alespoň jednu sezonu.")
elif not selected:
    st.info("Vyber hráče z vybraného týmu.")
else:
    lookup={p["name"]:p for p in roster}
    rows=[]; details=[]

    for name in selected:
        total,home,away,l5,l10,l20=analyze(
            lookup[name]["id"],
            [SEASONS[x] for x in selected_seasons],
            opponent
        )
        value=(total[2]/100)*odds-1 if total[2] else 0
        rows.append({
            "Hráč":name,
            "1+ G":total[0],
            "GP":total[1],
            "%":round(total[2],1),
            "Fair":round(total[3],2),
            "Value":f"{value*100:+.1f}%"
        })
        details.append({
            "Hráč":name,
            "L5":f"{l5[0]}/{l5[1]} ({l5[2]:.1f}%)",
            "L10":f"{l10[0]}/{l10[1]} ({l10[2]:.1f}%)",
            "L20":f"{l20[0]}/{l20[1]} ({l20[2]:.1f}%)",
            "Doma":f"{home[0]}/{home[1]} ({home[2]:.1f}%)",
            "Venku":f"{away[0]}/{away[1]} ({away[2]:.1f}%)"
        })

    result_df=pd.DataFrame(rows).sort_values(["%","1+ G"],ascending=False)

    st.subheader("🏆 Výsledek")
    st.dataframe(result_df,hide_index=True,use_container_width=True)

    st.subheader("📈 Forma a domácí/venkovní")
    st.dataframe(pd.DataFrame(details),hide_index=True,use_container_width=True)

    st.caption(
        "1+ G = počet zápasů s alespoň 1 gólem. "
        "Fair = 1 / pravděpodobnost. "
        "Value = (historická pravděpodobnost × nabízený kurz) − 1."
    )

    if len(selected) >= 2:
        st.subheader("🆚 Porovnání hráčů")
        comparison = result_df[["Hráč","%","Fair","Value"]].copy()
        st.dataframe(comparison,hide_index=True,use_container_width=True)

    csv=result_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Stáhnout CSV",csv,"nhl_goal_analysis.csv","text/csv")
