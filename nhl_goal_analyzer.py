import requests
import pandas as pd
import streamlit as st

BASE = "https://api-web.nhle.com/v1"

st.set_page_config(page_title="NHL Goal-Game Analyzer", layout="wide")
st.title("🏒 NHL Goal-Game Analyzer")
st.caption("Počítá zápasy s alespoň jedním gólem přímo z NHL Web API.")

def get_json(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=3600)
def player_log(player_id, season):
    data = get_json(f"{BASE}/player/{player_id}/game-log/{season}/2")
    games = data.get("gameLog", [])
    rows = []
    for g in games:
        rows.append({
            "date": g.get("gameDate", ""),
            "opponent": g.get("opponentAbbrev", ""),
            "goals": int(g.get("goals", g.get("G", 0)) or 0)
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=3600)
def leaders(season, n):
    data = get_json(f"{BASE}/skater-stats-leaders/{season}/2")
    items = []
    if isinstance(data, dict):
        if isinstance(data.get("goals"), list):
            items = data["goals"]
        elif isinstance(data.get("categories"), dict):
            items = data["categories"].get("goals", [])
        elif isinstance(data.get("skaters"), list):
            items = data["skaters"]
    elif isinstance(data, list):
        items = data

    out = []
    for x in items:
        pid = x.get("id") or x.get("playerId")
        name = x.get("name") or x.get("playerName") or str(pid)
        if isinstance(name, dict):
            name = name.get("default") or str(pid)
        goals = x.get("value", x.get("goals", x.get("G")))
        if pid is not None and goals is not None:
            out.append({"playerId": int(pid), "Hráč": name, "G": int(goals)})
    if not out:
        raise RuntimeError("NHL API vrátil jiný formát lídrů. Endpoint: /skater-stats-leaders/{season}/2")
    return pd.DataFrame(out).sort_values("G", ascending=False).head(n)

def analyze(pid, name, season):
    log = player_log(pid, season)
    gp = len(log)
    one_plus = int((log["goals"] >= 1).sum()) if gp else 0
    goals = int(log["goals"].sum()) if gp else 0
    return gp, goals, one_plus

season_map = {"2025/26": 20252026, "2024/25": 20242025, "2023/24": 20232024}
s1 = st.sidebar.selectbox("Sezóna 1", list(season_map), index=0)
s2 = st.sidebar.selectbox("Sezóna 2", list(season_map), index=1)
n = st.sidebar.slider("TOP N střelců", 5, 100, 30)

if st.button("▶ Spustit analýzu"):
    seasons = [season_map[s1], season_map[s2]]
    players = {}
    for s in seasons:
        for _, r in leaders(s, n).iterrows():
            players[int(r.playerId)] = r["Hráč"]

    rows = []
    progress = st.progress(0)
    for i, (pid, name) in enumerate(players.items(), 1):
        a = analyze(pid, name, seasons[0])
        b = analyze(pid, name, seasons[1])
        gp = a[0] + b[0]
        one = a[2] + b[2]
        rows.append({
            "Hráč": name,
            f"{s1} 1+": a[2],
            f"{s1} GP": a[0],
            f"{s2} 1+": b[2],
            f"{s2} GP": b[0],
            "1+ celkem": one,
            "GP celkem": gp,
            "% 2 sezony": round(one / gp * 100, 2) if gp else 0
        })
        progress.progress(i / len(players))

    result = pd.DataFrame(rows).sort_values("% 2 sezony", ascending=False)
    st.dataframe(result, use_container_width=True, hide_index=True)
    st.download_button(
        "Stáhnout CSV",
        result.to_csv(index=False).encode("utf-8-sig"),
        "nhl_goal_game_analysis.csv",
        "text/csv"
    )

st.info("Game type 2 = základní část. Zápas se počítá jednou, pokud goals >= 1.")
