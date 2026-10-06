
import requests
import pandas as pd
import streamlit as st

BASE = "https://api-web.nhle.com/v1"

st.set_page_config(
    page_title="NHL Goal-Game Analyzer",
    page_icon="🏒",
    layout="wide",
)

st.title("🏒 NHL Goal-Game Analyzer")
st.caption("Analýza zápasů s alespoň 1 gólem přímo z NHL Web API.")

SEASON_MAP = {
    "2025/26": 20252026,
    "2024/25": 20242025,
    "2023/24": 20232024,
}


def get_json(url):
    r = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 NHL Goal Analyzer"},
    )
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=3600)
def player_log(player_id, season):
    data = get_json(f"{BASE}/player/{player_id}/game-log/{season}/2")
    games = data.get("gameLog", [])

    rows = []
    for g in games:
        goals = g.get("goals", g.get("G", 0)) or 0

        # NHL Web API normally exposes homeRoad as H/R.
        # Fallbacks make the app more tolerant of API changes.
        venue_raw = (
            g.get("homeRoad")
            or g.get("homeRoadFlag")
            or g.get("venue")
            or ""
        )
        venue_raw = str(venue_raw).upper()

        if venue_raw in {"H", "HOME"}:
            venue = "Doma"
        elif venue_raw in {"R", "A", "AWAY", "ROAD"}:
            venue = "Venku"
        elif g.get("isHome") is True:
            venue = "Doma"
        elif g.get("isHome") is False:
            venue = "Venku"
        else:
            venue = "Neznámé"

        rows.append(
            {
                "date": pd.to_datetime(g.get("gameDate", ""), errors="coerce"),
                "opponent": g.get("opponentAbbrev", "") or "",
                "venue": venue,
                "goals": int(goals),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date", ascending=False).reset_index(drop=True)
    return df


@st.cache_data(ttl=3600)
def leaders(season, n):
    url = f"{BASE}/skater-stats-leaders/{season}/2?categories=goals&limit={max(n, 100)}"
    data = get_json(url)

    items = []
    if isinstance(data, dict):
        if isinstance(data.get("goals"), list):
            items = data["goals"]
        elif isinstance(data.get("categories"), dict):
            items = data["categories"].get("goals", [])
        elif isinstance(data.get("skaters"), list):
            items = data["skaters"]
        elif isinstance(data.get("data"), list):
            items = data["data"]
    elif isinstance(data, list):
        items = data

    out = []
    for x in items:
        pid = x.get("id") or x.get("playerId")
        name = x.get("name") or x.get("playerName") or str(pid)

        if isinstance(name, dict):
            name = name.get("default") or name.get("en") or str(pid)

        goals = x.get("value", x.get("goals", x.get("G")))
        team = (
            x.get("teamAbbrev")
            or x.get("team")
            or x.get("teamAbbreviation")
            or ""
        )

        if pid is not None and goals is not None:
            out.append(
                {
                    "playerId": int(pid),
                    "Hráč": str(name),
                    "Tým": str(team),
                    "G": int(goals),
                }
            )

    if not out:
        raise RuntimeError(
            "NHL API vrátil neočekávaný formát lídrů. "
            "Zkontroluj endpoint skater-stats-leaders."
        )

    return (
        pd.DataFrame(out)
        .drop_duplicates("playerId")
        .sort_values(["G", "Hráč"], ascending=[False, True])
        .head(n)
        .reset_index(drop=True)
    )


def filter_log(df, last_n, venue, opponent):
    if df.empty:
        return df

    result = df.copy()

    if venue != "Vše":
        result = result[result["venue"] == venue]

    if opponent != "Všichni":
        result = result[result["opponent"] == opponent]

    # Last N is applied AFTER venue/opponent filters, so it answers:
    # "How did the player perform in his last N relevant games?"
    if last_n != "Vše":
        result = result.head(int(last_n))

    return result


def stats_from_log(df):
    gp = len(df)
    one_plus = int((df["goals"] >= 1).sum()) if gp else 0
    goals = int(df["goals"].sum()) if gp else 0
    pct = round(one_plus / gp * 100, 1) if gp else 0.0
    fair = round(100 / pct, 2) if pct else None
    return gp, one_plus, goals, pct, fair


# ---------------- Sidebar ----------------

st.sidebar.header("⚙️ Nastavení")

s1 = st.sidebar.selectbox("Sezóna 1", list(SEASON_MAP), index=0)
s2 = st.sidebar.selectbox("Sezóna 2", list(SEASON_MAP), index=1)

n = st.sidebar.slider("TOP N střelců", 5, 100, 30, step=5)

period = st.sidebar.selectbox(
    "Období výsledku",
    [
        "Obě sezóny dohromady",
        "Pouze sezóna 1",
        "Pouze sezóna 2",
    ],
)

last_n = st.sidebar.selectbox(
    "Počet posledních relevantních zápasů",
    ["Vše", 20, 10],
)

venue = st.sidebar.selectbox(
    "Doma / venku",
    ["Vše", "Doma", "Venku"],
)

require_both = st.sidebar.checkbox(
    "Jen hráči, kteří byli v TOP N v obou sezónách",
    value=False,
)

st.sidebar.caption(
    "Zápas se započítá právě jednou, pokud hráč v daném zápase dal ≥ 1 gól."
)

# ---------------- Analysis ----------------

if st.button("▶ Spustit analýzu", use_container_width=True):

    seasons = [SEASON_MAP[s1], SEASON_MAP[s2]]

    with st.spinner("Načítám střelce a jejich game logy z NHL..."):
        try:
            l1 = leaders(seasons[0], n)
            l2 = leaders(seasons[1], n)
        except Exception as e:
            st.error(f"NHL API se nepodařilo načíst: {e}")
            st.stop()

        p1 = {
            int(r.playerId): {
                "name": r["Hráč"],
                "team": r["Tým"],
            }
            for _, r in l1.iterrows()
        }
        p2 = {
            int(r.playerId): {
                "name": r["Hráč"],
                "team": r["Tým"],
            }
            for _, r in l2.iterrows()
        }

        if require_both:
            player_ids = sorted(set(p1) & set(p2))
        else:
            player_ids = sorted(set(p1) | set(p2))

        if not player_ids:
            st.warning("Pro zvolené nastavení nebyli nalezeni žádní hráči.")
            st.stop()

        all_logs = {}
        progress = st.progress(0)

        for i, pid in enumerate(player_ids, start=1):
            try:
                all_logs[(pid, seasons[0])] = player_log(pid, seasons[0])
                all_logs[(pid, seasons[1])] = player_log(pid, seasons[1])
            except Exception as e:
                all_logs[(pid, seasons[0])] = pd.DataFrame()
                all_logs[(pid, seasons[1])] = pd.DataFrame()
                st.warning(f"Nelze načíst game log hráče ID {pid}: {e}")

            progress.progress(i / len(player_ids))

    # Opponent options are taken from all loaded game logs.
    opponents = set()
    for df in all_logs.values():
        if not df.empty:
            opponents.update(
                x for x in df["opponent"].dropna().astype(str).unique() if x
            )

    opponent = st.selectbox(
        "Soupeř",
        ["Všichni"] + sorted(opponents),
        help="Filtruje pouze zápasy proti vybranému soupeři.",
    )

    rows = []

    for pid in player_ids:
        meta = p1.get(pid) or p2.get(pid)
        name = meta["name"]
        team = meta["team"]

        df1 = filter_log(all_logs.get((pid, seasons[0]), pd.DataFrame()), last_n, venue, opponent)
        df2 = filter_log(all_logs.get((pid, seasons[1]), pd.DataFrame()), last_n, venue, opponent)

        if period == "Pouze sezóna 1":
            df = df1
            label = s1
            gp, one_plus, goals, pct, fair = stats_from_log(df)
            rows.append(
                {
                    "Hráč": name,
                    "Tým": team,
                    "Období": label,
                    "G": goals,
                    "1+": one_plus,
                    "GP": gp,
                    "% 1+": pct,
                    "Fair kurz": fair,
                }
            )

        elif period == "Pouze sezóna 2":
            df = df2
            label = s2
            gp, one_plus, goals, pct, fair = stats_from_log(df)
            rows.append(
                {
                    "Hráč": name,
                    "Tým": team,
                    "Období": label,
                    "G": goals,
                    "1+": one_plus,
                    "GP": gp,
                    "% 1+": pct,
                    "Fair kurz": fair,
                }
            )

        else:
            combined = pd.concat([df1, df2], ignore_index=True)
            if not combined.empty:
                combined = combined.sort_values("date", ascending=False).reset_index(drop=True)

            # For a combined two-season view, "last 10/20" means
            # the last 10/20 games across both selected seasons.
            if last_n != "Vše":
                combined = combined.head(int(last_n))

            gp, one_plus, goals, pct, fair = stats_from_log(combined)

            rows.append(
                {
                    "Hráč": name,
                    "Tým": team,
                    "Období": f"{s1} + {s2}",
                    "G": goals,
                    "1+": one_plus,
                    "GP": gp,
                    "% 1+": pct,
                    "Fair kurz": fair,
                }
            )

    result = pd.DataFrame(rows)

    if result.empty:
        st.warning("Žádná data.")
        st.stop()

    result = result[result["GP"] > 0].copy()

    if result.empty:
        st.warning("Pro zvolené filtry nebyly nalezeny žádné odehrané zápasy.")
        st.stop()

    result = result.sort_values(
        ["% 1+", "1+", "G"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    st.subheader("📊 Výsledky")

    st.dataframe(
        result,
        use_container_width=True,
        hide_index=True,
        column_config={
            "% 1+": st.column_config.NumberColumn(
                "% zápasů s gólem",
                format="%.1f %%",
            ),
            "Fair kurz": st.column_config.NumberColumn(
                "Fair kurz",
                format="%.2f",
            ),
        },
    )

    # Compact mobile-friendly top cards.
    st.subheader("🏆 Nejlepší výsledky")

    top = result.head(10)

    for _, r in top.iterrows():
        fair_text = f"{r['Fair kurz']:.2f}" if pd.notna(r["Fair kurz"]) else "—"
        st.markdown(
            f"**{r['Hráč']}** ({r['Tým']})  \n"
            f"{int(r['1+'])}/{int(r['GP'])} zápasů s gólem = "
            f"**{r['% 1+']:.1f}%** · Fair kurz **{fair_text}**"
        )

    csv = result.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        "⬇️ Stáhnout výsledky CSV",
        csv,
        "nhl_goal_game_analysis.csv",
        "text/csv",
        use_container_width=True,
    )

    st.info(
        "Fair kurz je orientační převod historické frekvence: "
        "100 / % zápasů s alespoň 1 gólem. Nezohledňuje kurzy sázkové kanceláře, "
        "sestavu, zranění ani aktuální formu."
    )

else:
    st.info(
        "Nastav sezóny a filtry a stiskni „Spustit analýzu“. "
        "Data se načítají přímo z NHL Web API."
    )
