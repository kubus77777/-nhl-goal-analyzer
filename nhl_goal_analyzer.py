import streamlit as st
import requests
import pandas as pd

BASE = "https://api-web.nhle.com/v1"

TEAMS = {
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

SEASONS = {
    "2024/25":"20242025",
    "2025/26":"20252026",
    "2026/27":"20262027"
}

st.set_page_config(page_title="NHL Goal Analyzer", page_icon="🏒", layout="centered")

@st.cache_data(ttl=3600)
def get_json(url):
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    return r.json()

def player_name(obj):
    first = obj.get("firstName", {})
    last = obj.get("lastName", {})
    if isinstance(first, dict):
        first = first.get("default", "")
    if isinstance(last, dict):
        last = last.get("default", "")
    return f"{first} {last}".strip()

@st.cache_data(ttl=86400)
def team_roster(team, season):
    data = get_json(f"{BASE}/roster/{team}/{season}")
    players = []
    for key in ("forwards", "defensemen", "goalies"):
        for p in data.get(key, []):
            if p.get("id"):
                players.append({
                    "id": int(p["id"]),
                    "name": player_name(p),
                    "pos": p.get("positionCode", ""),
                    "team": team
                })
    return list({p["id"]: p for p in players}.values())

@st.cache_data(ttl=3600)
def player_log(player_id, season):
    return get_json(f"{BASE}/player/{player_id}/game-log/{season}/2")

def parse_games(data):
    result = []
    for g in data.get("gameLog", data.get("games", [])):
        home_road = str(g.get("homeRoad", g.get("homeRoadFlag", ""))).upper()
        result.append({
            "goals": int(g.get("goals", g.get("G", 0)) or 0),
            "home": home_road in ("H", "HOME"),
            "opponent": str(
                g.get("opponentTeamAbbrev")
                or g.get("opponentAbbrev")
                or g.get("opponent")
                or ""
            ).upper(),
            "date": str(g.get("gameDate") or g.get("date") or "")
        })
    return result

def stats(games):
    gp = len(games)
    goal_games = sum(g["goals"] >= 1 for g in games)
    pct = goal_games / gp * 100 if gp else 0
    fair = 100 / pct if pct else 0
    return goal_games, gp, pct, fair

@st.cache_data(ttl=600)
def all_games(player_id, seasons_tuple):
    result = []
    for season in seasons_tuple:
        try:
            result.extend(parse_games(player_log(player_id, season)))
        except Exception:
            pass
    return sorted(result, key=lambda x: x["date"])

def analyze(games, opponent=None):
    if opponent:
        games = [g for g in games if g["opponent"] == opponent]
    home = [g for g in games if g["home"]]
    away = [g for g in games if not g["home"]]
    return {
        "total": stats(games),
        "home": stats(home),
        "away": stats(away),
        "l5": stats(games[-5:]),
        "l10": stats(games[-10:])
    }

def fmt(s):
    return f"{s[0]}/{s[1]} ({s[2]:.1f}%)"

# Fetch a sufficiently broad pool of goal leaders. For combined seasons,
# the union is then aggregated across all selected seasons.
@st.cache_data(ttl=3600)
def goal_leaders(season, limit=100):
    url = f"{BASE}/skater-stats-leaders/{season}/2?categories=goals&limit={limit}"
    data = get_json(url)
    if isinstance(data, list):
        return data
    for key in ("goals", "leaders", "skaterStatsLeaders", "data"):
        if isinstance(data.get(key), list):
            return data[key]
    return []

def leader_id(x):
    return x.get("id") or x.get("playerId")

def leader_goals(x):
    value = x.get("value", x.get("goals", x.get("G", 0)))
    try:
        return int(value)
    except Exception:
        return 0

def leader_team(x):
    return str(x.get("teamAbbrev") or x.get("teamAbbreviation") or x.get("team") or "")

def leader_display_name(x):
    return x.get("name") or x.get("playerName") or player_name(x) or str(leader_id(x))

def is_forward(player_id):
    try:
        data = get_json(f"{BASE}/player/{player_id}/landing")
        return data.get("position") in ("C", "L", "R", "F")
    except Exception:
        return False

st.title("🏒 NHL Goal Analyzer")
st.caption("Základní metrika: % zápasů, ve kterých hráč vstřelil alespoň 1 gól.")

mode = st.radio(
    "Režim",
    ["Hráči jednoho týmu", "TOP 50 střelců"],
    horizontal=True
)

if mode == "Hráči jednoho týmu":
    team_names = list(TEAMS)
    team_name = st.selectbox(
        "1. Tým",
        team_names,
        index=team_names.index("Montreal Canadiens")
    )
    team = TEAMS[team_name]

    season_labels = st.multiselect(
        "2. Sezony",
        list(SEASONS),
        default=["2024/25", "2025/26"]
    )

    if not season_labels:
        st.warning("Vyber alespoň jednu sezonu.")
        st.stop()

    only_forwards = st.checkbox("Pouze útočníci")

    roster_season = SEASONS["2026/27"] if "2026/27" in season_labels else SEASONS["2025/26"]
    try:
        roster = team_roster(team, roster_season)
    except Exception:
        roster = team_roster(team, SEASONS["2025/26"])

    if only_forwards:
        roster = [p for p in roster if p["pos"] in ("C", "L", "R", "F")]

    selected_names = st.multiselect(
        "3. Hráči",
        [p["name"] for p in roster],
        placeholder="Vyber jednoho nebo více hráčů"
    )

    opponents = ["Všichni soupeři"] + sorted(set(TEAMS.values()) - {team})
    opponent_choice = st.selectbox("4. Soupeř", opponents)
    opponent = None if opponent_choice == "Všichni soupeři" else opponent_choice

    if selected_names:
        lookup = {p["name"]: p for p in roster}
        seasons_tuple = tuple(SEASONS[s] for s in season_labels)
        rows = []

        for name in selected_names:
            gs = all_games(lookup[name]["id"], seasons_tuple)
            a = analyze(gs, opponent)
            rows.append({
                "Hráč": name,
                "1+ G": a["total"][0],
                "GP": a["total"][1],
                "%": round(a["total"][2], 1),
                "Fair": round(a["total"][3], 2),
                "L5": fmt(a["l5"]),
                "L10": fmt(a["l10"]),
                "Doma": fmt(a["home"]),
                "Venku": fmt(a["away"])
            })

        st.dataframe(
            pd.DataFrame(rows).sort_values(["%", "1+ G"], ascending=False),
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("Vyber hráče.")

else:
    st.subheader("🏆 TOP 50 střelců NHL")

    selected_top_seasons = st.multiselect(
        "Sezony pro TOP 50",
        list(SEASONS),
        default=["2025/26"]
    )

    only_forwards = st.checkbox("Pouze útočníci")

    if not selected_top_seasons:
        st.warning("Vyber alespoň jednu sezonu.")
        st.stop()

    season_ids = tuple(SEASONS[s] for s in selected_top_seasons)

    try:
        # For a combined ranking, collect a broad candidate pool from every
        # selected season, then aggregate goals across the selected seasons.
        candidates = {}
        for season_id in season_ids:
            for x in goal_leaders(season_id, 100):
                pid = leader_id(x)
                if pid:
                    pid = int(pid)
                    candidates[pid] = {
                        "name": leader_display_name(x),
                        "team": leader_team(x)
                    }

        rows = []
        for pid, info in candidates.items():
            if only_forwards and not is_forward(pid):
                continue

            combined_games = all_games(pid, season_ids)
            if not combined_games:
                continue

            total = stats(combined_games)
            rows.append({
                "Hráč": info["name"],
                "Tým": info["team"],
                "G": sum(g["goals"] for g in combined_games),
                "1+ G": total[0],
                "GP": total[1],
                "%": round(total[2], 1),
                "Fair": round(total[3], 2)
            })

        df = pd.DataFrame(rows).sort_values(
            ["G", "1+ G"], ascending=False
        ).head(50)

        label = " + ".join(selected_top_seasons)
        st.caption(f"TOP 50 podle celkového počtu gólů: {label}")
        st.dataframe(df, hide_index=True, use_container_width=True)

    except Exception as e:
        st.error("NHL API momentálně nevrátilo očekávaná data pro TOP 50.")
        st.caption(str(e))

st.divider()
st.caption(
    "Zdroj: NHL API. Pouze základní část. Každý zápas, ve kterém hráč vstřelil "
    "alespoň 1 gól, se počítá právě jednou."
)
