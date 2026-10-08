import streamlit as st
import requests
import pandas as pd

BASE = "https://api-web.nhle.com/v1"
STATS_BASE = "https://api.nhle.com/stats/rest/en"

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

# Mobilní / iPhone vzhled
st.html("""
<style>
/* Kompaktnější rozložení pro iPhone */
[data-testid="stAppViewContainer"] .main .block-container {
    padding-top: 1rem;
    padding-bottom: 2rem;
    padding-left: 0.7rem;
    padding-right: 0.7rem;
    max-width: 100%;
}
[data-testid="stHeader"] {
    background: transparent;
}
footer { visibility: hidden; }
[data-testid="stDataFrame"] {
    max-width: 100%;
}
@media (max-width: 600px) {
    h1 { font-size: 1.8rem !important; line-height: 1.1 !important; }
    h2 { font-size: 1.35rem !important; }
    h3 { font-size: 1.15rem !important; }
    p, label, [data-testid="stCaptionContainer"] { font-size: 0.92rem; }
}
</style>
""")

@st.cache_data(ttl=3600)
def get_json(url):
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=900)
def stats_json(url):
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=900)
def player_pp_stats(player_id, season="20262027"):
    """Season PP stats from NHL Stats REST: PP goals, PP time, PP shots."""
    try:
        exp = f"seasonId={season} and gameTypeId=2 and playerId={int(player_id)}"
        url = f"{STATS_BASE}/skater/powerplay"
        data = stats_json(url + "?cayenneExp=" + requests.utils.quote(exp, safe="" ) + "&limit=1")
        rows = data.get("data", []) if isinstance(data, dict) else []
        if not rows:
            return {"pp_goals": 0, "pp_toi": 0, "pp_shots": 0}
        row = rows[0]
        return {
            "pp_goals": _to_int(row.get("ppGoals", row.get("powerPlayGoals", 0))),
            "pp_toi": _toi_seconds(row.get("ppTimeOnIce", row.get("powerPlayTimeOnIce", ""))),
            "pp_shots": _to_int(row.get("ppShots", row.get("shots", 0))),
        }
    except Exception:
        # Fallback for PP goals from the game log if the stats endpoint is unavailable.
        try:
            games = parse_games(player_log(player_id, season))
            return {"pp_goals": sum(g["pp_goals"] for g in games), "pp_toi": 0, "pp_shots": 0}
        except Exception:
            return {"pp_goals": 0, "pp_toi": 0, "pp_shots": 0}

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

def _to_int(value):
    try:
        return int(value)
    except Exception:
        return 0

def _toi_seconds(value):
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text or ":" not in text:
        return 0
    try:
        m, sec = text.split(":", 1)
        return int(m) * 60 + int(sec)
    except Exception:
        return 0

def _fmt_toi(seconds):
    if not seconds:
        return "—"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"

def parse_games(data):
    result = []
    for g in data.get("gameLog", data.get("games", [])):
        home_road = str(g.get("homeRoad", g.get("homeRoadFlag", ""))).upper()
        result.append({
            "goals": _to_int(g.get("goals", g.get("G", 0))),
            "shots": _to_int(g.get("shots", g.get("SOG", g.get("shotsOnGoal", 0)))),
            "toi_seconds": _toi_seconds(g.get("toi", g.get("timeOnIce", ""))),
            "pp_goals": _to_int(g.get("powerPlayGoals", g.get("ppGoals", g.get("PPG", 0)))),
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

@st.cache_data(ttl=600)
def recent_player_games(player_id, n=5):
    all_recent = []
    # Start with the current season and roll back if fewer than n games exist.
    for season in ("20262027", "20252026", "20242025"):
        try:
            all_recent.extend(parse_games(player_log(player_id, season)))
        except Exception:
            pass
        if len(all_recent) >= n:
            break
    all_recent.sort(key=lambda x: x["date"], reverse=True)
    return all_recent[:n]

def recent_player_metrics(player_id, n=5):
    games = recent_player_games(player_id, n)
    if not games:
        return None, None
    avg_toi = sum(g["toi_seconds"] for g in games) / len(games)
    avg_shots = sum(g["shots"] for g in games) / len(games)
    # Keep both values numeric so table sorting is truly numeric.
    return round(avg_toi / 60, 1), round(avg_shots, 1)

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

def pct_value(s):
    return round(float(s[2]), 1) if s and len(s) >= 3 else None

# Fetch a sufficiently broad pool of goal leaders. For combined seasons,
# the union is then aggregated across all selected seasons.
@st.cache_data(ttl=900)
def season_powerplay_goals(player_id, season="20262027"):
    return player_pp_stats(player_id, season)["pp_goals"]

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
    # NHL calendar day is defined in Eastern Time.
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
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


@st.cache_data(ttl=600)
def current_season_player_games(player_id, n=5):
    """Last n completed regular-season games from 2026/27 only."""
    try:
        games = parse_games(player_log(player_id, "20262027"))
        games = [g for g in games if g.get("date")]
        games.sort(key=lambda x: x["date"], reverse=True)
        return games[:n]
    except Exception:
        return []

def _minmax_score(value, values):
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return 0.0
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return 50.0
    return (float(value) - lo) / (hi - lo) * 100.0

def _form_score(player_rows):
    """Current-form score: goals 35%, goal-games 25%, shots 20%, TOI 20%."""
    if not player_rows:
        return []

    goal_values = [r["goals"] for r in player_rows]
    goal_game_values = [r["goal_games"] / r["gp"] * 100 for r in player_rows]
    shot_values = [r["sog"] for r in player_rows]
    toi_values = [r["toi"] for r in player_rows]

    scored = []
    for r in player_rows:
        goal_rate = r["goal_games"] / r["gp"] * 100 if r["gp"] else 0
        score = (
            0.35 * _minmax_score(r["goals"], goal_values)
            + 0.25 * _minmax_score(goal_rate, goal_game_values)
            + 0.20 * _minmax_score(r["sog"], shot_values)
            + 0.20 * _minmax_score(r["toi"], toi_values)
        )
        rr = dict(r)
        rr["form_score"] = round(score, 1)
        rr["goal_rate"] = goal_rate
        scored.append(rr)

    return sorted(
        scored,
        key=lambda x: (x["form_score"], x["goals"], x["goal_games"], x["sog"]),
        reverse=True
    )

def player_trend_metrics(player_id):
    """L5 vs 2026/27 season trends for goal-game rate and shots/game."""
    try:
        season_games = parse_games(player_log(player_id, "20262027"))
        season_games = [g for g in season_games if g.get("date")]
        l5 = current_season_player_games(player_id, 5)
        sgp = len(season_games)
        l5gp = len(l5)
        season_goal_pct = (sum(g["goals"] >= 1 for g in season_games) / sgp * 100) if sgp else 0
        l5_goal_pct = (sum(g["goals"] >= 1 for g in l5) / l5gp * 100) if l5gp else 0
        season_sog = (sum(g["shots"] for g in season_games) / sgp) if sgp else 0
        l5_sog = (sum(g["shots"] for g in l5) / l5gp) if l5gp else 0
        return {
            "goal_pct_season": season_goal_pct,
            "goal_pct_l5": l5_goal_pct,
            "goal_trend": l5_goal_pct - season_goal_pct,
            "sog_season": season_sog,
            "sog_l5": l5_sog,
            "sog_trend": l5_sog - season_sog,
        }
    except Exception:
        return {"goal_pct_season": 0, "goal_pct_l5": 0, "goal_trend": 0, "sog_season": 0, "sog_l5": 0, "sog_trend": 0}

def pp_score_for_player(pp):
    """Raw PP factor inputs; normalized later against the relevant pool."""
    return (pp.get("pp_goals", 0), pp.get("pp_toi", 0), pp.get("pp_shots", 0))

@st.cache_data(ttl=600)
def daily_form_tips():
    """Pick 3 in-form forwards for every team playing today, with PP and trend factors."""
    try:
        games = today_games()
    except Exception:
        return []

    teams_today, opponents = [], {}
    for game in games:
        away, home = game_teams(game)
        if away and home:
            opponents[away] = home
            opponents[home] = away
            for team in (away, home):
                if team not in teams_today:
                    teams_today.append(team)

    opponent_ga = {}
    for team in teams_today:
        opp = opponents.get(team)
        try:
            rates = team_goal_rates(opp) if opp else None
            opponent_ga[team] = rates["ga"] if rates else None
        except Exception:
            opponent_ga[team] = None

    all_candidates = []
    team_candidate_map = {}
    for team in teams_today:
        try:
            roster = team_roster(team, "20262027")
        except Exception:
            try:
                roster = team_roster(team, "20252026")
            except Exception:
                roster = []
        roster = [p for p in roster if p.get("pos") in ("C", "L", "R", "F")]
        candidates = []
        for p in roster:
            games5 = current_season_player_games(p["id"], 5)
            # Prefer >=2 games, but allow one-game players only if necessary to keep teams represented.
            if not games5:
                continue
            gp = len(games5)
            goals = sum(g["goals"] for g in games5)
            goal_games = sum(g["goals"] >= 1 for g in games5)
            sog = sum(g["shots"] for g in games5)
            avg_toi = sum(g["toi_seconds"] for g in games5) / gp / 60.0
            try:
                season_games = [g for g in parse_games(player_log(p["id"], "20262027")) if g.get("date")]
                sgp = len(season_games)
                season_goal_rate = sum(g["goals"] >= 1 for g in season_games) / sgp * 100 if sgp else 0
            except Exception:
                season_goal_rate = 0
            pp = player_pp_stats(p["id"], "20262027")
            trend = player_trend_metrics(p["id"])
            row = {
                "id": p["id"], "name": p["name"], "team": team, "gp": gp,
                "goals": goals, "goal_games": goal_games, "sog": sog, "toi": avg_toi,
                "season_goal_rate": season_goal_rate, "pp_goals": pp["pp_goals"],
                "pp_toi": pp["pp_toi"], "pp_shots": pp["pp_shots"], **trend
            }
            candidates.append(row)
            all_candidates.append(row)
        team_candidate_map[team] = candidates

    # Build league-wide normalizers for the extra factors.
    season_values = [r["season_goal_rate"] for r in all_candidates]
    sogpg_values = [r["sog"] / r["gp"] for r in all_candidates if r["gp"]]
    pp_goal_values = [r["pp_goals"] for r in all_candidates]
    pp_toi_values = [r["pp_toi"] for r in all_candidates]
    pp_shot_values = [r["pp_shots"] for r in all_candidates]
    goal_trend_values = [r["goal_trend"] for r in all_candidates]
    shot_trend_values = [r["sog_trend"] for r in all_candidates]
    opp_values = [v for v in opponent_ga.values() if v is not None]

    all_rows = []
    for team in teams_today:
        candidates = team_candidate_map.get(team, [])
        if not candidates:
            continue
        scored = _form_score(candidates)
        for r in scored:
            season_component = _minmax_score(r["season_goal_rate"], season_values)
            sog_component = _minmax_score(r["sog"] / r["gp"], sogpg_values)
            opp_component = _minmax_score(opponent_ga.get(team), opp_values) if opponent_ga.get(team) is not None else 50.0
            pp_component = (
                0.40 * _minmax_score(r["pp_goals"], pp_goal_values)
                + 0.35 * _minmax_score(r["pp_toi"], pp_toi_values)
                + 0.25 * _minmax_score(r["pp_shots"], pp_shot_values)
            )
            trend_component = (
                0.60 * _minmax_score(r["goal_trend"], goal_trend_values)
                + 0.40 * _minmax_score(r["sog_trend"], shot_trend_values)
            )
            r["pp_score"] = round(pp_component, 1)
            r["trend_score"] = round(trend_component, 1)
            # Goal Score: form 50%, season scoring 15%, shots 10%, PP 15%, trend 5%, opponent 5%.
            r["goal_score"] = round(
                0.50 * r["form_score"] + 0.15 * season_component + 0.10 * sog_component
                + 0.15 * pp_component + 0.05 * trend_component + 0.05 * opp_component, 1
            )
        scored.sort(key=lambda x: (x["goal_score"], x["form_score"], x["goals"], x["goal_games"]), reverse=True)
        for rank, r in enumerate(scored[:3], start=1):
            all_rows.append({
                "Tým": team, "Pořadí": rank, "Hráč": r["name"],
                "Forma": r["form_score"], "Goal Score": r["goal_score"],
                "Trend G": r["goal_trend"], "Trend SOG": r["sog_trend"],
                "PP Score": r["pp_score"], "PP G": r["pp_goals"],
                "PP TOI": round(r["pp_toi"] / 60, 1), "PP SOG": r["pp_shots"],
                "G L5": r["goals"], "G-zápasy": f'{r["goal_games"]}/{r["gp"]}',
                "SOG/G": r["sog"] / r["gp"], "IT5_sec": r["toi"] * 60,
            })
    all_rows.sort(key=lambda x: (x["Tým"], -x["Goal Score"], -x["Forma"]))
    return all_rows

def daily_top10_goal_tips():
    rows = daily_form_tips()
    return sorted(rows, key=lambda x: (x["Goal Score"], x["Forma"], x["G L5"], x["SOG/G"]), reverse=True)[:10]


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
    "D/V rozdíl = domácí % − venkovní % (v procentních bodech). "
    "Číselné sloupce jsou řaditelné podle skutečné hodnoty, včetně desetinných míst."
)

st.subheader("🔥 Dnešní hráči ve formě")
st.caption(
    "Automaticky 3 útočníci z každého dnešního týmu. "
    "Forma: góly 35 % · zápasy s gólem 25 % · střely 20 % · ice time 20 %. "
    "Goal Score navíc zohledňuje sezónní % zápasů s gólem a obrannou slabost dnešního soupeře."
)

try:
    form_rows = daily_form_tips()
    if form_rows:
        form_df = pd.DataFrame(form_rows)
        form_df = form_df[
            ["Tým", "Pořadí", "Hráč", "Forma", "Goal Score", "Trend G", "Trend SOG",
             "PP Score", "PP G", "PP TOI", "PP SOG", "G L5", "G-zápasy", "SOG/G", "IT5_sec"]
        ]
        form_df = form_df.rename(columns={"IT5_sec": "IT5"})
        form_df["IT5"] = form_df["IT5"].fillna(0)

        # IT5 is converted to the requested mm:ss display format.
        display_df = form_df.copy()
        def fmt_toi(v):
            total = int(round(float(v)))
            return f"{total // 60}:{total % 60:02d}" if total else "—"
        display_df["IT5"] = display_df["IT5"].map(fmt_toi)

        st.dataframe(
            display_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Forma": st.column_config.NumberColumn("Forma", format="%.1f"),
                "Goal Score": st.column_config.NumberColumn("Goal Score", format="%.1f"),
                "Trend G": st.column_config.NumberColumn("Trend G", format="%+.1f"),
                "Trend SOG": st.column_config.NumberColumn("Trend SOG", format="%+.1f"),
                "PP Score": st.column_config.NumberColumn("PP Score", format="%.1f"),
                "PP G": st.column_config.NumberColumn("PP G", format="%d"),
                "PP TOI": st.column_config.NumberColumn("PP TOI (min)", format="%.1f"),
                "PP SOG": st.column_config.NumberColumn("PP SOG", format="%d"),
                "G L5": st.column_config.NumberColumn("G L5", format="%d"),
                "SOG/G": st.column_config.NumberColumn("SOG/G", format="%.1f"),
            }
        )
    else:
        st.info("Pro dnešní program se nepodařilo načíst aktuální formu hráčů.")
except Exception:
    st.info("Automatické tipy podle aktuální formy jsou momentálně nedostupné.")



try:
    st.subheader("🎯 TOP 10 dnešních gólových tipů")
    st.caption("Nejvyšší Goal Score napříč všemi dnešními týmy. Stejné vstupy jako ve formě, ale seřazené globálně.")
    top10_rows = daily_top10_goal_tips()
    if top10_rows:
        top10_df = pd.DataFrame(top10_rows)
        top10_df = top10_df[["Tým", "Hráč", "Goal Score", "Forma", "Trend G", "Trend SOG", "PP Score", "PP G", "PP TOI", "PP SOG", "G L5", "G-zápasy", "SOG/G", "IT5_sec"]]
        top10_df = top10_df.rename(columns={"IT5_sec": "IT5"})
        top10_df["IT5"] = top10_df["IT5"].map(lambda v: _fmt_toi(v) if v else "—")
        st.dataframe(top10_df, hide_index=True, use_container_width=True, column_config={
            "Goal Score": st.column_config.NumberColumn("Goal Score", format="%.1f"),
            "Forma": st.column_config.NumberColumn("Forma", format="%.1f"),
            "Trend G": st.column_config.NumberColumn("Trend G", format="%+.1f"),
            "Trend SOG": st.column_config.NumberColumn("Trend SOG", format="%+.1f"),
            "PP Score": st.column_config.NumberColumn("PP Score", format="%.1f"),
            "PP G": st.column_config.NumberColumn("PP G", format="%d"),
            "PP TOI": st.column_config.NumberColumn("PP TOI (min)", format="%.1f"),
            "PP SOG": st.column_config.NumberColumn("PP SOG", format="%d"),
            "G L5": st.column_config.NumberColumn("G L5", format="%d"),
            "SOG/G": st.column_config.NumberColumn("SOG/G", format="%.1f"),
        })
    else:
        st.info("Pro dnešní program nejsou dostupné tipy.")
except Exception:
    st.info("TOP 10 tipů je momentálně nedostupných.")


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
        index=None,
        placeholder="Vyber tým"
    )
    if not team_name:
        st.info("Vyber tým pro zobrazení hráčů.")
        st.stop()
    team = TEAMS[team_name]

    season_labels = st.multiselect(
        "2. Sezony",
        list(SEASONS),
        default=["2024/25", "2025/26"]
    )

    if not season_labels:
        st.warning("Vyber alespoň jednu sezonu.")
        st.stop()

    only_forwards = st.checkbox("Pouze útočníci", value=True)

    roster_season = SEASONS["2026/27"] if "2026/27" in season_labels else SEASONS["2025/26"]
    try:
        roster = team_roster(team, roster_season)
    except Exception:
        roster = team_roster(team, SEASONS["2025/26"])

    if only_forwards:
        roster = [p for p in roster if p["pos"] in ("C", "L", "R", "F")]

    roster_names = [p["name"] for p in roster]
    selected_names = st.multiselect(
        "3. Hráči",
        roster_names,
        default=roster_names,
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
                "L5": pct_value(a["l5"]),
                "L10": pct_value(a["l10"]),
                "Doma": pct_value(a["home"]),
                "Venku": pct_value(a["away"]),
                "D/V rozdíl": round(a["home"][2] - a["away"][2], 1),
                "IT5": recent_player_metrics(lookup[name]["id"])[0],
                "SOG5": recent_player_metrics(lookup[name]["id"])[1],
                "PP G 26/27": season_powerplay_goals(lookup[name]["id"]),
                "Trend G": round(player_trend_metrics(lookup[name]["id"])["goal_trend"], 1),
                "Trend SOG": round(player_trend_metrics(lookup[name]["id"])["sog_trend"], 1),
            })

        df_players = pd.DataFrame(rows).sort_values(["%", "1+ G"], ascending=[False, False])
        st.dataframe(
            df_players,
            hide_index=True,
            use_container_width=True,
            column_config={
                "%": st.column_config.NumberColumn("%", format="%.1f"),
                "Fair": st.column_config.NumberColumn("Fair", format="%.2f"),
                "L5": st.column_config.NumberColumn("L5 %", format="%.1f"),
                "L10": st.column_config.NumberColumn("L10 %", format="%.1f"),
                "Doma": st.column_config.NumberColumn("Doma %", format="%.1f"),
                "Venku": st.column_config.NumberColumn("Venku %", format="%.1f"),
                "D/V rozdíl": st.column_config.NumberColumn("D/V rozdíl", format="%+.1f"),
                "IT5": st.column_config.NumberColumn("IT5 (min)", format="%.1f"),
                "SOG5": st.column_config.NumberColumn("SOG5", format="%.1f"),
                "PP G 26/27": st.column_config.NumberColumn("PP G 26/27", format="%d"),
                "Trend G": st.column_config.NumberColumn("Trend G", format="%+.1f"),
                "Trend SOG": st.column_config.NumberColumn("Trend SOG", format="%+.1f"),
            }
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

    only_forwards = st.checkbox("Pouze útočníci", value=True)

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
                "Fair": round(total[3], 2),
                "D/V": round(
                    stats([g for g in combined_games if g["home"]])[2]
                    - stats([g for g in combined_games if not g["home"]])[2], 1
                ),
                "IT5": recent_player_metrics(pid)[0],
                "SOG5": recent_player_metrics(pid)[1],
                "PP G 26/27": season_powerplay_goals(pid),
                "PP TOI": round(player_pp_stats(pid)["pp_toi"] / 60, 1),
                "PP SOG": player_pp_stats(pid)["pp_shots"],
                "Trend G": round(player_trend_metrics(pid)["goal_trend"], 1),
                "Trend SOG": round(player_trend_metrics(pid)["sog_trend"], 1)
            })

        df = pd.DataFrame(rows).sort_values(
            ["%", "1+ G", "G"], ascending=[False, False, False]
        ).head(50)

        # Mobile-friendly column order: percentage immediately follows team abbreviation.
        df = df[["Hráč", "Tým", "%", "D/V", "Trend G", "Trend SOG", "IT5", "SOG5", "PP G 26/27", "PP TOI", "PP SOG", "1+ G", "GP", "G", "Fair"]]

        label = " + ".join(selected_top_seasons)
        location_label = {
            "Všechny zápasy": "všechny zápasy",
            "Doma": "domácí zápasy",
            "Venku": "venkovní zápasy"
        }[top_location]
        st.caption(
            f"TOP 50 podle % zápasů s gólem: {label} · {location_label}"
        )
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "%": st.column_config.NumberColumn("%", format="%.1f"),
                "D/V": st.column_config.NumberColumn("D/V", format="%+.1f"),
                "IT5": st.column_config.NumberColumn("IT5 (min)", format="%.1f"),
                "SOG5": st.column_config.NumberColumn("SOG5", format="%.1f"),
                "PP G 26/27": st.column_config.NumberColumn("PP G 26/27", format="%d"),
                "PP TOI": st.column_config.NumberColumn("PP TOI (min)", format="%.1f"),
                "PP SOG": st.column_config.NumberColumn("PP SOG", format="%d"),
                "Trend G": st.column_config.NumberColumn("Trend G", format="%+.1f"),
                "Trend SOG": st.column_config.NumberColumn("Trend SOG", format="%+.1f"),
                "Fair": st.column_config.NumberColumn("Fair", format="%.2f"),
            }
        )

    except Exception as e:
        st.error("NHL API momentálně nevrátilo očekávaná data pro TOP 50.")
        st.caption(str(e))



st.divider()

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
                "Oček. góly": round(x["Nejvyšší odhad"], 2),
                "Oček. góly soupeře": round(
                    x["Odhad domácích"] if x["Tým s potenciálem"] == x["Hosté"] else x["Odhad hostů"], 2
                )
            }
            for x in daily
        ])
        st.dataframe(
            daily_df, hide_index=True, use_container_width=True,
            column_config={
                "Oček. góly": st.column_config.NumberColumn("Oček. góly", format="%.2f"),
                "Oček. góly soupeře": st.column_config.NumberColumn("Oček. góly soupeře", format="%.2f"),
            }
        )
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
        st.dataframe(
            recent_df, hide_index=True, use_container_width=True,
            column_config={
                "GF/G L10": st.column_config.NumberColumn("GF/G L10", format="%.2f"),
                "GA/G soupeře L10": st.column_config.NumberColumn("GA/G soupeře L10", format="%.2f"),
                "Odhad gólů": st.column_config.NumberColumn("Odhad gólů", format="%.2f"),
            }
        )
    else:
        st.info("Pro některé dnešní týmy se nepodařilo načíst posledních 10 dokončených zápasů.")
except Exception:
    st.info("Analýza posledních 10 zápasů je momentálně nedostupná.")

st.divider()
st.caption(
    "Zdroj: NHL API. Pouze základní část. Každý zápas, ve kterém hráč vstřelil "
    "alespoň 1 gól, se počítá právě jednou."
)
