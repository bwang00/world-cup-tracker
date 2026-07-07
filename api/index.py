"""
FIFA World Cup 2026 Tracker — FastAPI on Vercel
Cron: hourly fetch of fixtures/scores from API-Football
Dashboard: Scores & Schedule | Predictions (tabbed)
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(
    title="World Cup 2026 Tracker",
    version="2.0.0",
)

# --------------------------------------------------------------------------- #
# Config                                                                      #
# --------------------------------------------------------------------------- #
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "")
API_BASE = "https://v3.football.api-sports.io"
WORLD_CUP_LEAGUE_ID = 1  # FIFA World Cup
WORLD_CUP_SEASON = 2026

# Vercel doesn't have persistent filesystem in production, so we keep a
# lightweight in-memory cache that gets populated on cron runs (and survives
# within a single function instance's warm lifetime).
_cache: dict[str, Any] = {"fixtures": [], "last_updated": None, "season_label": ""}

# --------------------------------------------------------------------------- #
# Predictions data                                                            #
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
# Helpers — fetch from API-Football                                           #
# --------------------------------------------------------------------------- #
def _api_get(endpoint: str, params: dict[str, str] | None = None) -> dict:
    """Make a GET request to API-Football."""
    if not API_FOOTBALL_KEY:
        return {"response": []}
    qs = "&".join(f"{k}={v}" for k, v in (params or {}).items())
    url = f"{API_BASE}{endpoint}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(url, headers={"x-apisports-key": API_FOOTBALL_KEY})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def fetch_fixtures() -> tuple[list[dict], str]:
    """Fetch World Cup 2026 fixtures. Falls back to 2022 if 2026 has no data yet."""
    data = _api_get("/fixtures", {
        "league": str(WORLD_CUP_LEAGUE_ID),
        "season": str(WORLD_CUP_SEASON),
    })
    season_label = "2026"
    # If 2026 has no fixtures yet, fall back to 2022 as reference data
    if not data.get("response"):
        data = _api_get("/fixtures", {
            "league": str(WORLD_CUP_LEAGUE_ID),
            "season": "2022",
        })
        season_label = "2022 (reference — 2026 schedule not yet published)"
    fixtures = []
    for item in data.get("response", []):
        fixture = item.get("fixture", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        league = item.get("league", {})
        fixtures.append({
            "id": fixture.get("id"),
            "date": fixture.get("date", ""),
            "status": fixture.get("status", {}).get("short", "TBD"),
            "status_long": fixture.get("status", {}).get("long", ""),
            "venue": fixture.get("venue", {}).get("name", ""),
            "city": fixture.get("venue", {}).get("city", ""),
            "round": league.get("round", ""),
            "home": {
                "name": teams.get("home", {}).get("name", "TBD"),
                "logo": teams.get("home", {}).get("logo", ""),
            },
            "away": {
                "name": teams.get("away", {}).get("name", "TBD"),
                "logo": teams.get("away", {}).get("logo", ""),
            },
            "score_home": goals.get("home"),
            "score_away": goals.get("away"),
        })
    fixtures.sort(key=lambda f: f["date"])
    return fixtures, season_label


# --------------------------------------------------------------------------- #
# Cron endpoint — called daily by Vercel Cron (7am Beijing / 23:00 UTC)                                #
# --------------------------------------------------------------------------- #
TOURNAMENT_END = date(2026, 7, 20)  # day after the final


@app.get("/api/cron")
def cron(request: Request):
    """Vercel Cron handler: refresh fixtures cache daily at 7am Beijing time.
    Automatically stops fetching once the tournament is over (after July 19, 2026)."""
    today = date.today()
    if today > TOURNAMENT_END:
        return {
            "ok": True,
            "skipped": True,
            "reason": "Tournament ended on 2026-07-19. Cron is inactive.",
            "last_updated": _cache.get("last_updated"),
        }
    fixtures, season_label = fetch_fixtures()
    _cache["fixtures"] = fixtures
    _cache["season_label"] = season_label
    _cache["last_updated"] = datetime.now(timezone.utc).isoformat()
    return {
        "ok": True,
        "fetched": len(fixtures),
        "season": season_label,
        "last_updated": _cache["last_updated"],
    }


# --------------------------------------------------------------------------- #
# API endpoints                                                               #
# --------------------------------------------------------------------------- #
@app.get("/api")
def api_root():
    days = (date(2026, 6, 11) - date.today()).days
    return {
        "name": "World Cup 2026 Tracker",
        "version": "2.0.0",
        "days_until_kickoff": max(days, 0),
        "endpoints": ["/api/health", "/api/fixtures", "/api/predictions", "/api/cron"],
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "last_updated": _cache.get("last_updated")}


@app.get("/api/fixtures")
def fixtures_endpoint():
    return {"count": len(_cache["fixtures"]), "last_updated": _cache["last_updated"], "items": _cache["fixtures"]}


@app.get("/api/predictions")
def predictions_endpoint():
    ranked = sorted(PREDICTIONS, key=lambda p: p["chance"], reverse=True)
    return {"count": len(ranked), "items": ranked}


# --------------------------------------------------------------------------- #
# HTML Dashboard                                                              #
# --------------------------------------------------------------------------- #
def _render_fixtures_html(fixtures: list[dict]) -> str:
    if not fixtures:
        return """
        <div class="empty-state">
          <p class="empty-icon">&#9917;</p>
          <h3>No fixture data yet</h3>
          <p>The cron job fetches scores hourly from API-Football once the tournament schedule is published.<br>
          If you just deployed, trigger a manual refresh at <a href="/api/cron">/api/cron</a>.</p>
          <p class="hint">Make sure the <code>API_FOOTBALL_KEY</code> environment variable is set in Vercel.</p>
        </div>"""

    # Group by round
    rounds: dict[str, list] = {}
    for f in fixtures:
        r = f.get("round") or "Scheduled"
        rounds.setdefault(r, []).append(f)

    html = ""
    for rnd, matches in rounds.items():
        html += f'<h3 class="round-header">{rnd}</h3><div class="matches">'
        for m in matches:
            dt = m["date"][:16].replace("T", " ") if m["date"] else "TBD"
            sh = m["score_home"]
            sa = m["score_away"]
            score_display = f'{sh} - {sa}' if sh is not None else "vs"
            status_class = "live" if m["status"] in ("1H", "2H", "HT", "ET", "P", "LIVE") else (
                "ft" if m["status"] in ("FT", "AET", "PEN") else "")
            status_label = m["status_long"] or m["status"]
            html += f'''
            <div class="match-card {status_class}">
              <div class="match-time">{dt} <span class="status-badge {status_class}">{status_label}</span></div>
              <div class="match-teams">
                <div class="team home">
                  {'<img src="'+m["home"]["logo"]+'" class="team-logo"/>' if m["home"]["logo"] else ''}
                  <span>{m["home"]["name"]}</span>
                </div>
                <div class="score">{score_display}</div>
                <div class="team away">
                  <span>{m["away"]["name"]}</span>
                  {'<img src="'+m["away"]["logo"]+'" class="team-logo"/>' if m["away"]["logo"] else ''}
                </div>
              </div>
              <div class="match-venue">{m["venue"]}{", " + m["city"] if m["city"] else ""}</div>
            </div>'''
        html += '</div>'
    return html


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
    days = (date(2026, 6, 11) - date.today()).days
    last_upd = _cache.get("last_updated") or "never"
    season_label = _cache.get("season_label") or "no data yet"
    fixtures_html = _render_fixtures_html(_cache["fixtures"])
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
    .countdown{{background:linear-gradient(135deg,#fbbf24,#f97316);color:#1a0f00;padding:5px 12px;border-radius:999px;font-weight:700;font-size:11px}}

    /* Tabs */
    .tabs{{display:flex;gap:4px;margin-bottom:20px;background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:12px;padding:4px;width:fit-content}}
    .tab{{padding:8px 18px;border-radius:9px;font-size:13px;font-weight:500;cursor:pointer;transition:all .15s;color:var(--muted);border:none;background:none}}
    .tab.active{{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#0b1220;font-weight:600;box-shadow:0 2px 8px rgba(34,211,238,.25)}}
    .tab:hover:not(.active){{color:var(--text)}}
    .tab-panel{{display:none}}
    .tab-panel.active{{display:block}}

    /* Fixtures */
    .round-header{{margin:20px 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent2)}}
    .matches{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:10px}}
    .match-card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;transition:border-color .12s}}
    .match-card:hover{{border-color:var(--accent)}}
    .match-card.live{{border-color:var(--live);box-shadow:0 0 12px rgba(239,68,68,.15)}}
    .match-card.ft{{opacity:.85}}
    .match-time{{font-size:11px;color:var(--muted);margin-bottom:8px;display:flex;align-items:center;gap:8px}}
    .status-badge{{padding:2px 7px;border-radius:5px;font-size:10px;font-weight:600;text-transform:uppercase}}
    .status-badge.live{{background:var(--live);color:#fff}}
    .status-badge.ft{{background:rgba(255,255,255,.1);color:var(--muted)}}
    .match-teams{{display:flex;align-items:center;justify-content:space-between;gap:8px}}
    .team{{display:flex;align-items:center;gap:6px;font-size:13px;font-weight:500;flex:1}}
    .team.away{{justify-content:flex-end;text-align:right}}
    .team-logo{{width:20px;height:20px;border-radius:2px}}
    .score{{font-size:18px;font-weight:700;min-width:50px;text-align:center;color:var(--accent)}}
    .match-venue{{font-size:11px;color:var(--muted);margin-top:6px}}

    /* Empty state */
    .empty-state{{text-align:center;padding:48px 20px;color:var(--muted)}}
    .empty-state .empty-icon{{font-size:48px;margin-bottom:8px}}
    .empty-state h3{{color:var(--text);margin:0 0 8px}}
    .empty-state p{{margin:4px 0;font-size:13px}}
    .empty-state .hint{{margin-top:14px;font-size:11px;color:var(--muted)}}
    .empty-state code{{background:rgba(255,255,255,.08);padding:2px 6px;border-radius:4px;font-size:11px}}

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
      <span class="countdown">{"&#9917; LIVE" if days <= 0 else f"{days} days to kickoff"}</span>
      <span class="chip">48 teams</span>
      <span class="chip">Updated daily 7am Beijing</span>
    </div>
  </header>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('scores')">Scores &amp; Schedule</button>
    <button class="tab" onclick="switchTab('predictions')">Predictions</button>
  </div>

  <div id="tab-scores" class="tab-panel active">
    {fixtures_html}
    <p class="update-note">Season: {season_label} &middot; Last refreshed: {last_upd} &middot; Cron: daily 7am Beijing</p>
  </div>

  <div id="tab-predictions" class="tab-panel">
    <p style="color:var(--muted);font-size:12px;margin-bottom:14px;">Heuristic power ratings (0-100) and title-probability estimates based on squad depth, recent form, and pedigree.</p>
    {predictions_html}
  </div>

  <footer>
    <a href="/api">/api</a> &middot; <a href="/api/fixtures">/api/fixtures</a> &middot; <a href="/api/predictions">/api/predictions</a> &middot; <a href="/api/cron">/api/cron</a>
    <br>Powered by API-Football &middot; Predictions for entertainment only
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
    # Lazy-load: if cache is empty (cold start), fetch fixtures now
    if not _cache["fixtures"] and API_FOOTBALL_KEY:
        try:
            fixtures, season_label = fetch_fixtures()
            _cache["fixtures"] = fixtures
            _cache["season_label"] = season_label
            _cache["last_updated"] = datetime.now(timezone.utc).isoformat()
        except Exception:
            pass
    return HTMLResponse(render_dashboard())
