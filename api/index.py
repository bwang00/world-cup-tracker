"""
FIFA World Cup 2026 Tracker — FastAPI on Vercel
Data source: https://worldcup26.ir (free, no auth)
Cron: daily 7am Beijing time (23:00 UTC)
Dashboard: Scores & Schedule | Predictions (tabbed)
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timezone
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(
    title="World Cup 2026 Tracker",
    version="3.0.0",
)

# --------------------------------------------------------------------------- #
# Config                                                                      #
# --------------------------------------------------------------------------- #
API_BASE = "https://worldcup26.ir/get"
TOURNAMENT_END = date(2026, 7, 20)

# In-memory cache (survives within a warm function instance)
_cache: dict[str, Any] = {
    "games": [],
    "teams": {},
    "groups": [],
    "last_updated": None,
}

# --------------------------------------------------------------------------- #
# Predictions                                                                 #
# --------------------------------------------------------------------------- #
PREDICTIONS = [
    {"team": "Argentina", "flag": "\U0001f1e6\U0001f1f7", "rating": 92, "chance": 15.5,
     "reason": "Reigning champions, elite midfield, Messi legacy plus Julian Alvarez peaking."},
    {"team": "France", "flag": "\U0001f1eb\U0001f1f7", "rating": 91, "chance": 14.0,
     "reason": "Mbappe at his peak; deepest attacking pool in Europe; finalists in 2018 and 2022."},
    {"team": "Brazil", "flag": "\U0001f1e7\U0001f1f7", "rating": 89, "chance": 12.0,
     "reason": "New generation (Vinicius, Rodrygo, Endrick) plus Ancelotti's tactical structure."},
    {"team": "England", "flag": "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f", "rating": 87, "chance": 10.5,
     "reason": "Bellingham-Foden-Saka triangle is world-class; keeper depth is the swing factor."},
    {"team": "Spain", "flag": "\U0001f1ea\U0001f1f8", "rating": 86, "chance": 9.0,
     "reason": "Euro 2024 champions; Yamal and Nico Williams electrify wide play."},
    {"team": "Portugal", "flag": "\U0001f1f5\U0001f1f9", "rating": 82, "chance": 6.0,
     "reason": "Ronaldo's swan song, but the engine is now Bruno, Vitinha and Bernardo."},
    {"team": "Germany", "flag": "\U0001f1e9\U0001f1ea", "rating": 81, "chance": 5.5,
     "reason": "Musiala-Wirtz axis plus Kimmich veteran presence; defense still the question."},
    {"team": "Netherlands", "flag": "\U0001f1f3\U0001f1f1", "rating": 80, "chance": 4.5,
     "reason": "Van Dijk-led defense; Gakpo and Reijnders progression give a balanced side."},
    {"team": "Morocco", "flag": "\U0001f1f2\U0001f1e6", "rating": 78, "chance": 3.5,
     "reason": "2022 semifinalists; deepest African squad; defense unmatched at AFCON."},
    {"team": "Belgium", "flag": "\U0001f1e7\U0001f1ea", "rating": 76, "chance": 3.0,
     "reason": "Golden generation faded, but De Bruyne and Doku still make them dangerous."},
    {"team": "Uruguay", "flag": "\U0001f1fa\U0001f1fe", "rating": 77, "chance": 3.0,
     "reason": "Bielsa's press plus Nunez/Pellistri front line; Copa America form encouraging."},
    {"team": "Italy", "flag": "\U0001f1ee\U0001f1f9", "rating": 75, "chance": 2.5,
     "reason": "Returning after two missed cycles; midfield strong, striker crisis unresolved."},
    {"team": "United States", "flag": "\U0001f1fa\U0001f1f8", "rating": 73, "chance": 2.5,
     "reason": "Home advantage worth ~5% swing; Pulisic-McKennie-Reyna core in prime."},
    {"team": "Colombia", "flag": "\U0001f1e8\U0001f1f4", "rating": 74, "chance": 2.0,
     "reason": "James's renaissance and Luis Diaz make them a knockout-round threat."},
    {"team": "Croatia", "flag": "\U0001f1ed\U0001f1f7", "rating": 72, "chance": 2.0,
     "reason": "Modric winding down but tactical maturity keeps them dangerous."},
    {"team": "Mexico", "flag": "\U0001f1f2\U0001f1fd", "rating": 70, "chance": 1.5,
     "reason": "Host status, but generational transition still incomplete."},
    {"team": "Japan", "flag": "\U0001f1ef\U0001f1f5", "rating": 71, "chance": 1.2,
     "reason": "Best Asian side by a distance; Mitoma-Kubo-Kamada trio thrives in Europe."},
    {"team": "Senegal", "flag": "\U0001f1f8\U0001f1f3", "rating": 70, "chance": 1.0,
     "reason": "Physicality plus Mendy in goal; needs Sarr/Jackson to click up top."},
    {"team": "Denmark", "flag": "\U0001f1e9\U0001f1f0", "rating": 69, "chance": 0.7,
     "reason": "Hjulmand's structure plus Hojlund/Eriksen give them a puncher's chance."},
    {"team": "Switzerland", "flag": "\U0001f1e8\U0001f1ed", "rating": 67, "chance": 0.4,
     "reason": "Reliable knockout-round attendee, but ceiling looks like quarterfinals."},
]


# --------------------------------------------------------------------------- #
# Data fetching                                                               #
# --------------------------------------------------------------------------- #
def _fetch_json(endpoint: str) -> Any:
    url = f"{API_BASE}/{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": "WorldCupTracker/3.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def refresh_cache() -> dict:
    """Fetch games, teams, and groups from worldcup26.ir."""
    games_data = _fetch_json("games")
    teams_data = _fetch_json("teams")
    groups_data = _fetch_json("groups")

    games = games_data.get("games", games_data) if isinstance(games_data, dict) else games_data
    teams_list = teams_data.get("teams", teams_data) if isinstance(teams_data, dict) else teams_data
    groups = groups_data.get("groups", groups_data) if isinstance(groups_data, dict) else groups_data

    # Build team lookup by id
    teams_map = {}
    for t in teams_list:
        teams_map[t.get("id", t.get("_id"))] = t

    _cache["games"] = games
    _cache["teams"] = teams_map
    _cache["groups"] = groups
    _cache["last_updated"] = datetime.now(timezone.utc).isoformat()

    return {
        "ok": True,
        "games": len(games),
        "teams": len(teams_map),
        "groups": len(groups),
        "last_updated": _cache["last_updated"],
    }


# --------------------------------------------------------------------------- #
# Cron endpoint                                                               #
# --------------------------------------------------------------------------- #
@app.get("/api/cron")
def cron():
    """Daily cron (7am Beijing / 23:00 UTC). Stops after tournament ends."""
    if date.today() > TOURNAMENT_END:
        return {"ok": True, "skipped": True, "reason": "Tournament ended 2026-07-19."}
    return refresh_cache()


# --------------------------------------------------------------------------- #
# API endpoints                                                               #
# --------------------------------------------------------------------------- #
@app.get("/api")
def api_root():
    return {
        "name": "World Cup 2026 Tracker",
        "version": "3.0.0",
        "source": "worldcup26.ir",
        "endpoints": ["/", "/api/health", "/api/games", "/api/predictions", "/api/cron"],
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "last_updated": _cache.get("last_updated"), "cached_games": len(_cache["games"])}


@app.get("/api/games")
def games_endpoint():
    return {"count": len(_cache["games"]), "last_updated": _cache["last_updated"], "items": _cache["games"]}


@app.get("/api/predictions")
def predictions_endpoint():
    ranked = sorted(PREDICTIONS, key=lambda p: p["chance"], reverse=True)
    return {"count": len(ranked), "items": ranked}


# --------------------------------------------------------------------------- #
# HTML Dashboard                                                              #
# --------------------------------------------------------------------------- #
ROUND_ORDER = {"group": 0, "r32": 1, "r16": 2, "qf": 3, "sf": 4, "3rd": 5, "final": 6}
ROUND_LABELS = {"group": "Group Stage", "r32": "Round of 32", "r16": "Round of 16",
                "qf": "Quarterfinals", "sf": "Semifinals", "3rd": "Third Place", "final": "Final"}


def _render_games_html(games: list[dict]) -> str:
    if not games:
        return '<div class="empty-state"><p class="empty-icon">&#9917;</p><h3>No data yet</h3><p>Trigger <a href="/api/cron">/api/cron</a> to fetch.</p></div>'

    # Separate by status
    live = [g for g in games if g.get("finished") != "TRUE" and g.get("time_elapsed") not in ("not_started", None, "")]
    finished = [g for g in games if g.get("finished") == "TRUE"]
    upcoming = [g for g in games if g.get("finished") != "TRUE" and g.get("time_elapsed") in ("not_started", None, "")]

    # Sort finished by date descending (most recent first)
    finished.sort(key=lambda g: g.get("local_date", ""), reverse=True)
    upcoming.sort(key=lambda g: g.get("local_date", ""))

    html = ""

    # Live matches first
    if live:
        html += '<h3 class="section-header live-pulse">LIVE NOW</h3><div class="matches">'
        for g in live:
            html += _match_card(g, is_live=True)
        html += '</div>'

    # Recent results (last 16)
    if finished:
        html += '<h3 class="section-header">Recent Results</h3><div class="matches">'
        for g in finished[:16]:
            html += _match_card(g, is_live=False)
        html += '</div>'

    # Upcoming
    if upcoming:
        html += '<h3 class="section-header">Upcoming</h3><div class="matches">'
        for g in upcoming[:8]:
            html += _match_card(g, is_live=False, upcoming=True)
        html += '</div>'

    return html


def _match_card(g: dict, is_live: bool = False, upcoming: bool = False) -> str:
    home = g.get("home_team_name_en", "TBD")
    away = g.get("away_team_name_en", "TBD")
    hs = g.get("home_score", "-")
    aws = g.get("away_score", "-")
    dt = g.get("local_date", "TBD")
    round_type = g.get("type", "group")
    round_label = ROUND_LABELS.get(round_type, round_type.upper())
    time_el = g.get("time_elapsed", "")
    group = g.get("group", "")

    status_class = "live" if is_live else ("ft" if not upcoming else "upcoming")
    if is_live:
        status_text = f"LIVE {time_el}'" if time_el else "LIVE"
    elif upcoming:
        status_text = "Upcoming"
        hs = ""
        aws = ""
    else:
        status_text = "FT"

    score_display = f"{hs} - {aws}" if hs != "" else "vs"
    group_badge = f' <span class="group-badge">Group {group}</span>' if round_type == "group" and group else ""
    scorers_home = g.get("home_scorers", "")
    scorers_away = g.get("away_scorers", "")
    scorers_html = ""
    if scorers_home and scorers_home != "null" and not upcoming:
        scorers_html += f'<div class="scorers home-scorers">{_clean_scorers(scorers_home)}</div>'
    if scorers_away and scorers_away != "null" and not upcoming:
        scorers_html += f'<div class="scorers away-scorers">{_clean_scorers(scorers_away)}</div>'

    return f'''
    <div class="match-card {status_class}">
      <div class="match-meta">
        <span class="round-label">{round_label}{group_badge}</span>
        <span class="status-badge {status_class}">{status_text}</span>
      </div>
      <div class="match-teams">
        <div class="team home"><span class="team-name">{home}</span></div>
        <div class="score">{score_display}</div>
        <div class="team away"><span class="team-name">{away}</span></div>
      </div>
      {scorers_html}
      <div class="match-date">{dt}</div>
    </div>'''


def _clean_scorers(s: str) -> str:
    """Clean up scorer strings like {"Player 9'","Player 67'"}"""
    s = s.replace("{", "").replace("}", "").replace('"', '').replace("\u201c", "").replace("\u201d", "")
    return s


def _render_predictions_html() -> str:
    ranked = sorted(PREDICTIONS, key=lambda p: p["chance"], reverse=True)
    max_chance = ranked[0]["chance"]
    rows = ""
    for i, p in enumerate(ranked):
        bar_w = (p["chance"] / max_chance) * 100
        rows += f'''
        <tr>
          <td class="rank">{i+1}</td>
          <td class="team-cell"><span class="flag">{p["flag"]}</span> {p["team"]}</td>
          <td class="rating">{p["rating"]}</td>
          <td>
            <div class="bar-wrap">
              <div class="bar" style="width:{bar_w:.0f}%"></div>
              <span class="bar-label">{p["chance"]:.1f}%</span>
            </div>
          </td>
          <td class="reason">{p["reason"]}</td>
        </tr>'''
    return f'''
    <table class="pred-table">
      <thead><tr><th>#</th><th>Team</th><th>Rating</th><th>Title chance</th><th>Analysis</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>'''


def render_dashboard() -> str:
    games = _cache["games"]
    last_upd = _cache.get("last_updated") or "never"
    total = len(games)
    finished = sum(1 for g in games if g.get("finished") == "TRUE")
    live = sum(1 for g in games if g.get("finished") != "TRUE" and g.get("time_elapsed") not in ("not_started", None, ""))

    games_html = _render_games_html(games)
    predictions_html = _render_predictions_html()

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>World Cup 2026 Tracker</title>
  <style>
    :root {{
      --bg1:#0b1220;--bg2:#0f2a24;--card:#131b2e;--line:#1f2a44;
      --text:#e6edf6;--muted:#94a3b8;--accent:#22d3ee;--accent2:#34d399;
      --gold:#fbbf24;--live:#ef4444;
    }}
    *{{box-sizing:border-box}}
    html,body{{margin:0;padding:0;background:linear-gradient(160deg,var(--bg1),var(--bg2));color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;min-height:100vh}}
    .wrap{{max-width:1120px;margin:0 auto;padding:28px 20px 60px}}
    header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:28px}}
    .brand{{display:flex;align-items:center;gap:12px}}
    .badge{{width:48px;height:48px;border-radius:14px;background:linear-gradient(135deg,var(--accent),var(--accent2));display:grid;place-items:center;font-size:22px;font-weight:700;color:#0b1220}}
    h1{{margin:0;font-size:20px;letter-spacing:-.01em}}
    .sub{{color:var(--muted);font-size:12px}}
    .chips{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
    .chip{{background:rgba(255,255,255,.05);border:1px solid var(--line);padding:5px 11px;border-radius:999px;font-size:11px}}
    .chip.live{{background:rgba(239,68,68,.15);border-color:var(--live);color:var(--live);font-weight:600;animation:pulse 2s infinite}}
    @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.6}}}}

    /* Tabs */
    .tabs{{display:flex;gap:4px;margin-bottom:20px;background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:12px;padding:4px;width:fit-content}}
    .tab{{padding:8px 18px;border-radius:9px;font-size:13px;font-weight:500;cursor:pointer;transition:all .15s;color:var(--muted);border:none;background:none}}
    .tab.active{{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#0b1220;font-weight:600;box-shadow:0 2px 8px rgba(34,211,238,.25)}}
    .tab:hover:not(.active){{color:var(--text)}}
    .tab-panel{{display:none}}
    .tab-panel.active{{display:block}}

    /* Matches */
    .section-header{{margin:20px 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent2)}}
    .section-header.live-pulse{{color:var(--live);animation:pulse 2s infinite}}
    .matches{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}}
    .match-card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;transition:border-color .12s}}
    .match-card:hover{{border-color:var(--accent)}}
    .match-card.live{{border-color:var(--live);box-shadow:0 0 12px rgba(239,68,68,.15)}}
    .match-card.ft{{opacity:.9}}
    .match-meta{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
    .round-label{{font-size:11px;color:var(--muted)}}
    .group-badge{{background:rgba(34,211,238,.1);border:1px solid rgba(34,211,238,.2);padding:1px 6px;border-radius:4px;font-size:10px;color:var(--accent);margin-left:6px}}
    .status-badge{{padding:2px 8px;border-radius:5px;font-size:10px;font-weight:600;text-transform:uppercase}}
    .status-badge.live{{background:var(--live);color:#fff;animation:pulse 2s infinite}}
    .status-badge.ft{{background:rgba(255,255,255,.08);color:var(--muted)}}
    .status-badge.upcoming{{background:rgba(34,211,238,.1);color:var(--accent)}}
    .match-teams{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:8px 0}}
    .team{{flex:1;font-size:14px;font-weight:500}}
    .team.away{{text-align:right}}
    .score{{font-size:20px;font-weight:700;min-width:60px;text-align:center;color:var(--accent)}}
    .match-card.live .score{{color:var(--live)}}
    .scorers{{font-size:11px;color:var(--muted);margin:4px 0}}
    .match-date{{font-size:11px;color:var(--muted);margin-top:6px;padding-top:6px;border-top:1px solid var(--line)}}

    /* Empty */
    .empty-state{{text-align:center;padding:48px 20px;color:var(--muted)}}
    .empty-state .empty-icon{{font-size:48px}}
    .empty-state h3{{color:var(--text);margin:8px 0}}
    .empty-state a{{color:var(--accent)}}

    /* Predictions */
    .pred-table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}}
    .pred-table th,.pred-table td{{padding:11px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:12px;vertical-align:middle}}
    .pred-table thead th{{background:rgba(255,255,255,.03);font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}}
    .pred-table tr:last-child td{{border-bottom:none}}
    .rank{{font-weight:700;color:var(--gold);width:30px}}
    .team-cell{{font-weight:600;white-space:nowrap}}
    .flag{{font-size:16px;margin-right:4px}}
    .rating{{color:var(--accent2);font-weight:600;width:50px}}
    .bar-wrap{{position:relative;background:rgba(255,255,255,.05);border-radius:6px;height:20px;overflow:hidden;min-width:120px}}
    .bar{{background:linear-gradient(90deg,var(--accent2),var(--accent));height:100%}}
    .bar-label{{position:absolute;inset:0;display:grid;place-items:center;font-size:10px;font-weight:700}}
    .reason{{color:#94a3b8;font-size:11px;max-width:340px}}

    .update-note{{font-size:11px;color:var(--muted);margin-top:16px}}
    footer{{margin-top:32px;text-align:center;font-size:11px;color:var(--muted)}}
    footer a{{color:var(--accent);text-decoration:none}}
  </style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      <div class="badge">WC</div>
      <div>
        <h1>FIFA World Cup 2026 Tracker</h1>
        <div class="sub">USA &middot; Canada &middot; Mexico &middot; June 11 – July 19, 2026</div>
      </div>
    </div>
    <div class="chips">
      {'<span class="chip live">&#128308; ' + str(live) + ' LIVE</span>' if live > 0 else ''}
      <span class="chip">{finished}/{total} played</span>
      <span class="chip">48 teams</span>
    </div>
  </header>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('scores')">Scores &amp; Schedule</button>
    <button class="tab" onclick="switchTab('predictions')">Predictions</button>
  </div>

  <div id="tab-scores" class="tab-panel active">
    {games_html}
    <p class="update-note">Last refreshed: {last_upd} &middot; Cron: daily 7am Beijing &middot; Source: worldcup26.ir</p>
  </div>

  <div id="tab-predictions" class="tab-panel">
    <p style="color:var(--muted);font-size:12px;margin-bottom:14px;">Pre-tournament heuristic ratings (0-100) and title-probability estimates. Updated as tournament progresses.</p>
    {predictions_html}
  </div>

  <footer>
    <a href="/api">/api</a> &middot; <a href="/api/games">/api/games</a> &middot; <a href="/api/predictions">/api/predictions</a> &middot; <a href="/api/cron">/api/cron</a>
    <br>Data: <a href="https://worldcup26.ir" target="_blank">worldcup26.ir</a> (open source) &middot; Predictions for entertainment only
  </footer>
</div>
<script>
function switchTab(id) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  event.target.classList.add('active');
}}
</script>
</body>
</html>'''


@app.get("/", response_class=HTMLResponse)
def dashboard():
    # Lazy-load on cold start
    if not _cache["games"]:
        try:
            refresh_cache()
        except Exception:
            pass
    return HTMLResponse(render_dashboard())
