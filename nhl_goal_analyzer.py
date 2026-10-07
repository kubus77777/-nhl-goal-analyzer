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


from datetime import datetime
from zoneinfo import ZoneInfo

@st.cache_data(ttl=900)
def today_schedule():
    today = datetime.now(ZoneInfo("Europe/Prague")).date().isoformat()
    return get_json(f"{BASE}/schedule/{today}")

@st.cache_data(ttl=600)
def team_season_schedule(team, season):
    return get_json(f"{BASE}/club-schedule-season/{team}/{season}")

def _completed_team_games(team, data):
    games = _schedule_list(data)
    completed = []

    for g in games:
        if not isinstance(g, dict) or int(g.get("gameType", 0) or 0) != 2:
            continue
        state = str(g.get("gameState", g.get("gameStatus", ""))).upper()
        if state not in ("OFF", "FINAL", "FINALIZED"):
            continue

        away = g.get("awayTeam", {}) or {}
        home = g.get("homeTeam", {}) or {}
        away_code = _team_code(away)
        home_code = _team_code(home)
        if team not in (away_code, home_code):
            continue

        away_score = away.get("score")
        home_score = home.get("score")
        if not isinstance(away_score, (int, float)) or not isinstance(home_score, (int, float)):
            continue

        if team == away_code:
            gf, ga, home_flag = float(away_score), float(home_score), False
        else:
            gf, ga, home_flag = float(home_score), float(away_score), True

        completed.append({
            "date": str(g.get("gameDate") or g.get("date") or ""),
            "gf": gf, "ga": ga, "home": home_flag, "id": g.get("id")
        })
    return completed

@st.cache_data(ttl=900)
def team_goal_rates(team):
    total_gf = total_ga = total_gp = 0.0
    season_rows = []

    for season in SEASONS.values():
        try:
            games = _completed_team_games(team, team_season_schedule(team, season))
            if not games:
                continue
            gf = sum(g["gf"] for g in games)
            ga = sum(g["ga"] for g in games)
            gp = len(games)
            total_gp += gp
            total_gf += gf
            total_ga += ga
            season_rows.append((season, gf / gp, ga / gp))
        except Exception:
            continue

    if total_gp == 0:
        return None
    return {"gf": total_gf / total_gp, "ga": total_ga / total_gp,
            "gp": total_gp, "seasons": season_rows}

def schedule_games(data):
    games = []
    for day in data.get("gameWeek", []):
        if isinstance(day, dict):
            games.extend(day.get("games", []))
    if not games and isinstance(data.get("games"), list):
        games = data["games"]
    return games

def today_games():
    data = today_schedule()
    # NHL „dnešní zápasy“ určujeme podle data v Eastern Time (ET),
    # aby večerní zápasy v USA patřily ke správnému NHL dni i v ČR.
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    games = []
    for day in data.get("gameWeek", []):
        if isinstance(day, dict) and day.get("date") == today:
            games.extend(day.get("games", []))
    return games

def game_teams(game):
    away = game.get("awayTeam", {})
    home = game.get("homeTeam", {})
    return (
        away.get("abbrev") or away.get("triCode") or away.get("teamAbbrev"),
        home.get("abbrev") or home.get("triCode") or home.get("teamAbbrev")
    )

@st.cache_data(ttl=600)
def team_schedule_now(team):
    return get_json(f"{BASE}/club-schedule-season/{team}/now")

def _schedule_list(data):
    if not isinstance(data, dict):
        return []
    if isinstance(data.get("games"), list):
        return data["games"]
    games = []
    for day in data.get("gameWeek", []):
        if isinstance(day, dict) and isinstance(day.get("games"), list):
            games.extend(day["games"])
    return games

def _team_code(team_obj):
    if not isinstance(team_obj, dict):
        return ""
    return str(
        team_obj.get("abbrev")
        or team_obj.get("triCode")
        or team_obj.get("teamAbbrev")
        or ""
    ).upper()

@st.cache_data(ttl=600)
def recent_team_rates(team, n=10):
    try:
        all_games = []
        for season in ("20262027", "20252026", "20242025"):
            all_games.extend(_completed_team_games(team, team_season_schedule(team, season)))
            if len(all_games) >= n:
                break

        all_games.sort(key=lambda x: (x["date"], str(x.get("id", ""))), reverse=True)
        last = all_games[:n]
        if len(last) < n:
            return None

        return {
            "gp": len(last),
            "gf": sum(x["gf"] for x in last) / len(last),
            "ga": sum(x["ga"] for x in last) / len(last),
            "games": last,
        }
    except Exception:
        return None

def daily_last10_projection():
    try:
        games = today_games()
    except Exception:
        return []

    projections = []
    for game in games:
        away, home = game_teams(game)
        if not away or not home:
            continue

        a = recent_team_rates(away, 10)
        h = recent_team_rates(home, 10)
        if not a or not h or a["gp"] < 10 or h["gp"] < 10:
            continue

        away_xg = (a["gf"] + h["ga"]) / 2
        home_xg = (h["gf"] + a["ga"]) / 2

        projections.append({
            "Zápas": f"{away} @ {home}",
            "Hosté": away,
            "Domácí": home,
            "Hosté GF/G L10": a["gf"],
            "Hosté GA/G L10": a["ga"],
            "Domácí GF/G L10": h["gf"],
            "Domácí GA/G L10": h["ga"],
            "Odhad hostů": away_xg,
            "Odhad domácích": home_xg,
            "Nejvyšší odhad": max(away_xg, home_xg),
            "Tým s potenciálem": away if away_xg >= home_xg else home,
        })

    return sorted(projections, key=lambda x: x["Nejvyšší odhad"], reverse=True)

def daily_goal_projection():
    try:
        games = today_games()
    except Exception:
        return []

    projections = []
    for game in games:
        away, home = game_teams(game)
        if not away or not home:
            continue

        a = team_goal_rates(away)
        h = team_goal_rates(home)
        if not a or not h:
            continue

        # Team-specific expected goals:
        # attack strength of the team + defensive weakness of opponent, divided by 2.
        away_xg = (a["gf"] + h["ga"]) / 2
        home_xg = (h["gf"] + a["ga"]) / 2

        projections.append({
            "Zápas": f"{away} @ {home}",
            "Hosté": away,
            "Domácí": home,
            "Odhad hostů": away_xg,
            "Odhad domácích": home_xg,
            "Nejvyšší odhad": max(away_xg, home_xg),
            "Tým s potenciálem": away if away_xg >= home_xg else home
        })

    return sorted(projections, key=lambda x: x["Nejvyšší odhad"], reverse=True)

st.title("🏒 NHL Goal Analyzer")
st.caption(
    "Základní metrika: % zápasů, ve kterých hráč vstřelil alespoň 1 gól. "
    "D/V rozdíl = domácí % − venkovní % (v procentních bodech)."
)

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
                "Venku": fmt(a["away"]),
                "D/V rozdíl": f"{a["home"][2] - a["away"][2]:+.1f} p.b."
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

    top_location = st.radio(
        "Domácí / venkovní",
        ["Všechny zápasy", "Doma", "Venku"],
        horizontal=True
    )

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

            if top_location == "Doma":
                filtered_games = [g for g in combined_games if g["home"]]
            elif top_location == "Venku":
                filtered_games = [g for g in combined_games if not g["home"]]
            else:
                filtered_games = combined_games

            if not filtered_games:
                continue

            total = stats(filtered_games)
            rows.append({
                "Hráč": info["name"],
                "Tým": info["team"],
                "%": round(total[2], 1),
                "1+ G": total[0],
                "GP": total[1],
                "G": sum(g["goals"] for g in filtered_games),
                "Fair": round(total[3], 2)
            })

        df = pd.DataFrame(rows).sort_values(
            ["%", "1+ G", "G"], ascending=[False, False, False]
        ).head(50)

        # Mobile-friendly column order: percentage immediately follows team abbreviation.
        df = df[["Hráč", "Tým", "%", "1+ G", "GP", "G", "Fair"]]

        label = " + ".join(selected_top_seasons)
        location_label = {
            "Všechny zápasy": "všechny zápasy",
            "Doma": "domácí zápasy",
            "Venku": "venkovní zápasy"
        }[top_location]
        st.caption(
            f"TOP 50 podle % zápasů s gólem: {label} · {location_label}"
        )
        st.dataframe(df, hide_index=True, use_container_width=True)

    except Exception as e:
        st.error("NHL API momentálně nevrátilo očekávaná data pro TOP 50.")
        st.caption(str(e))


st.divider()
st.subheader("🔥 Dnešní zápasy – gólový potenciál týmu")
st.caption(
    "Sezona: 2024/25 + 2025/26 + 2026/27. Odhad konkrétního týmu = "
    "(jeho GF/G + GA/G soupeře) / 2."
)

try:
    daily = daily_goal_projection()
    if daily:
        daily_df = pd.DataFrame([
            {
                "Zápas": x["Zápas"],
                "Tým": x["Tým s potenciálem"],
                "Odhad gólů": round(x["Nejvyšší odhad"], 2),
                "Odhad 2. týmu": round(
                    x["Odhad domácích"] if x["Tým s potenciálem"] == x["Hosté"] else x["Odhad hostů"], 2
                )
            }
            for x in daily
        ])
        st.dataframe(daily_df, hide_index=True, use_container_width=True)
    else:
        st.info("Pro dnešní program se nepodařilo načíst kompletní týmová data.")
except Exception:
    st.info("Dnešní gólový potenciál je momentálně nedostupný.")

st.subheader("⚡ Dnešní zápasy – forma posledních 10 zápasů")
st.caption(
    "Pouze posledních 10 dokončených zápasů každého týmu. "
    "Odhad = (GF/G týmu za L10 + GA/G soupeře za L10) / 2. "
    "Zápasy se řadí podle nejvyššího odhadu gólů konkrétního týmu."
)

try:
    recent = daily_last10_projection()
    if recent:
        recent_df = pd.DataFrame([
            {
                "Zápas": x["Zápas"],
                "Tým": x["Tým s potenciálem"],
                "GF/G L10": round(
                    x["Hosté GF/G L10"] if x["Tým s potenciálem"] == x["Hosté"] else x["Domácí GF/G L10"], 2
                ),
                "GA/G soupeře L10": round(
                    x["Domácí GA/G L10"] if x["Tým s potenciálem"] == x["Hosté"] else x["Hosté GA/G L10"], 2
                ),
                "Odhad gólů": round(x["Nejvyšší odhad"], 2),
            }
            for x in recent
        ])
        st.dataframe(recent_df, hide_index=True, use_container_width=True)
    else:
        st.info("Pro některé dnešní týmy se nepodařilo načíst posledních 10 dokončených zápasů.")
except Exception:
    st.info("Analýza posledních 10 zápasů je momentálně nedostupná.")

st.divider()
st.caption(
    "Zdroj: NHL API. Pouze základní část. Každý zápas, ve kterém hráč vstřelil "
    "alespoň 1 gól, se počítá právě jednou."
)
