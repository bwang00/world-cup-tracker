"""
FIFA World Cup 2026 Tracker — FastAPI on Vercel
Data source: https://worldcup26.ir (free, no auth, real-time scores)
Cron: daily 7am Beijing time (23:00 UTC)
Dashboard: 3 tabs — Live/Results | Bracket | Predictions
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timezone, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="World Cup 2026 Tracker", version="4.0.0")

# --------------------------------------------------------------------------- #
# Config                                                                      #
# --------------------------------------------------------------------------- #
API_BASE = "https://worldcup26.ir/get"
TOURNAMENT_END = date(2026, 7, 20)
BJT = timezone(timedelta(hours=8))  # Beijing Time

_cache: dict[str, Any] = {"games": [], "teams": {}, "groups": [], "last_updated": None}

# --------------------------------------------------------------------------- #
# Updated Predictions — reflecting actual tournament performance (as of R16)  #
# --------------------------------------------------------------------------- #
PREDICTIONS = [
    {"team": "France", "flag": "\U0001f1eb\U0001f1f7", "rating": 95, "chance": 18.0,
     "status": "QF", "form": "W W W W W",
     "reason": "Dominant run: 3-0 Sweden (R32), 1-0 Paraguay (R16). Mbappe in terrifying form. Clear favorites now."},
    {"team": "Spain", "flag": "\U0001f1ea\U0001f1f8", "rating": 93, "chance": 16.0,
     "status": "QF", "form": "W W W W W",
     "reason": "3-0 Austria (R32), 1-0 Portugal (R16). Yamal unstoppable. Haven't conceded in knockouts."},
    {"team": "England", "flag": "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f", "rating": 91, "chance": 14.0,
     "status": "QF", "form": "W W W W W",
     "reason": "Beat DR Congo 2-1 (R32), thrilling 3-2 vs Mexico (R16). Attack firing on all cylinders."},
    {"team": "Morocco", "flag": "\U0001f1f2\U0001f1e6", "rating": 89, "chance": 12.0,
     "status": "QF", "form": "W D W W W",
     "reason": "3-0 Canada (R16). 2022 semifinal run was no fluke — defense still impenetrable."},
    {"team": "Belgium", "flag": "\U0001f1e7\U0001f1ea", "rating": 87, "chance": 10.0,
     "status": "QF", "form": "W W W W W",
     "reason": "Destroyed USA 4-1 (R16). De Bruyne renaissance; golden generation's last dance paying off."},
    {"team": "Norway", "flag": "\U0001f1f3\U0001f1f4", "rating": 86, "chance": 9.0,
     "status": "QF", "form": "W W W W W",
     "reason": "Stunned Brazil 2-1 (R16). Haaland has 5 goals. Dark horse turned genuine contender."},
    {"team": "Argentina", "flag": "\U0001f1e6\U0001f1f7", "rating": 84, "chance": 7.5,
     "status": "R16 (today)", "form": "W W W W",
     "reason": "Scraped past Cape Verde 3-2. Still alive but looked vulnerable. Playing Egypt today."},
    {"team": "Colombia", "flag": "\U0001f1e8\U0001f1f4", "rating": 78, "chance": 4.0,
     "status": "R16 (today)", "form": "W W W W",
     "reason": "Solid 1-0 vs Ghana (R32). Face Switzerland today. James pulling strings."},
    {"team": "Switzerland", "flag": "\U0001f1e8\U0001f1ed", "rating": 76, "chance": 3.0,
     "status": "R16 (today)", "form": "W W D W",
     "reason": "2-0 Algeria (R32). Reliable but face Colombia today in R16."},
    {"team": "Egypt", "flag": "\U0001f1ea\U0001f1ec", "rating": 72, "chance": 2.5,
     "status": "R16 (today)", "form": "D W D W",
     "reason": "Survived Australia on away goals (R32). Face Argentina today — huge underdog moment."},
    {"team": "Brazil", "flag": "\U0001f1e7\U0001f1f7", "rating": 0, "chance": 0,
     "status": "ELIMINATED (R16)", "form": "W W W W L",
     "reason": "Shocked by Norway 2-1. Endrick missed key chances. Tournament over."},
    {"team": "Portugal", "flag": "\U0001f1f5\U0001f1f9", "rating": 0, "chance": 0,
     "status": "ELIMINATED (R16)", "form": "W W W W L",
     "reason": "Lost 1-0 to Spain in Iberian derby. Ronaldo's last World Cup ends in tears."},
    {"team": "United States", "flag": "\U0001f1fa\U0001f1f8", "rating": 0, "chance": 0,
     "status": "ELIMINATED (R16)", "form": "W W W W L",
     "reason": "Overwhelmed 4-1 by Belgium. Home advantage couldn't save a porous defense."},
    {"team": "Mexico", "flag": "\U0001f1f2\U0001f1fd", "rating": 0, "chance": 0,
     "status": "ELIMINATED (R16)", "form": "W W W W L",
     "reason": "Heartbreaking 3-2 loss to England. Fought hard but fell short again."},
    {"team": "Canada", "flag": "\U0001f1e8\U0001f1e6", "rating": 0, "chance": 0,
     "status": "ELIMINATED (R16)", "form": "W W D W L",
     "reason": "Morocco proved too strong — 3-0 defeat. Still a historic run for Les Rouges."},
    {"team": "Germany", "flag": "\U0001f1e9\U0001f1ea", "rating": 0, "chance": 0,
     "status": "ELIMINATED (R32)", "form": "W W D D",
     "reason": "Drew Paraguay in R32, eliminated on penalties. Tournament curse continues."},
    {"team": "Netherlands", "flag": "\U0001f1f3\U0001f1f1", "rating": 0, "chance": 0,
     "status": "ELIMINATED (R32)", "form": "W W D D",
     "reason": "Drew Morocco in R32, lost on penalties. Van Dijk's generation running out of chances."},
    {"team": "Japan", "flag": "\U0001f1ef\U0001f1f5", "rating": 0, "chance": 0,
     "status": "ELIMINATED (R32)", "form": "W W W L",
     "reason": "Lost 2-1 to Brazil in R32. Competitive but couldn't break through."},
    {"team": "Croatia", "flag": "\U0001f1ed\U0001f1f7", "rating": 0, "chance": 0,
     "status": "ELIMINATED (R32)", "form": "W D W L",
     "reason": "Portugal edged them 2-1 in R32. End of the Modric era."},
    {"team": "Senegal", "flag": "\U0001f1f8\U0001f1f3", "rating": 0, "chance": 0,
     "status": "ELIMINATED (R32)", "form": "W W D L",
     "reason": "Fell 3-2 to Belgium in a thriller. Gave everything but couldn't hold on."},
]


# --------------------------------------------------------------------------- #
# Data fetching                                                               #
# --------------------------------------------------------------------------- #
def _fetch_json(endpoint: str) -> Any:
    url = f"{API_BASE}/{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": "WorldCupTracker/4.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def refresh_cache() -> dict:
    games_data = _fetch_json("games")
    teams_data = _fetch_json("teams")
    groups_data = _fetch_json("groups")

    games = games_data.get("games", games_data) if isinstance(games_data, dict) else games_data
    teams_list = teams_data.get("teams", teams_data) if isinstance(teams_data, dict) else teams_data
    groups = groups_data.get("groups", groups_data) if isinstance(groups_data, dict) else groups_data

    teams_map = {t.get("id", t.get("_id")): t for t in teams_list}

    _cache["games"] = games
    _cache["teams"] = teams_map
    _cache["groups"] = groups
    _cache["last_updated"] = datetime.now(timezone.utc).isoformat()

    return {"ok": True, "games": len(games), "teams": len(teams_map), "last_updated": _cache["last_updated"]}


def _to_beijing_time(date_str: str) -> str:
    """Convert 'MM/DD/YYYY HH:MM' (assumed local US Eastern) to Beijing time display."""
    # The API times appear to be US Eastern (UTC-4 during summer / EDT)
    # Convert: add 12 hours to get Beijing time (UTC+8 vs UTC-4 = +12)
    try:
        dt = datetime.strptime(date_str.strip(), "%m/%d/%Y %H:%M")
        dt_bjt = dt + timedelta(hours=12)
        return dt_bjt.strftime("%m/%d %H:%M BJT")
    except (ValueError, TypeError):
        return date_str or "TBD"


# --------------------------------------------------------------------------- #
# Cron                                                                        #
# --------------------------------------------------------------------------- #
@app.get("/api/cron")
def cron():
    if date.today() > TOURNAMENT_END:
        return {"ok": True, "skipped": True, "reason": "Tournament ended."}
    return refresh_cache()


# --------------------------------------------------------------------------- #
# API endpoints                                                               #
# --------------------------------------------------------------------------- #
@app.get("/api")
def api_root():
    return {"name": "World Cup 2026 Tracker", "version": "4.0.0", "source": "worldcup26.ir"}


@app.get("/api/health")
def health():
    return {"status": "ok", "last_updated": _cache.get("last_updated"), "cached_games": len(_cache["games"])}


@app.get("/api/games")
def games_endpoint():
    return {"count": len(_cache["games"]), "last_updated": _cache["last_updated"], "items": _cache["games"]}


@app.get("/api/predictions")
def predictions_endpoint():
    active = [p for p in PREDICTIONS if p["chance"] > 0]
    ranked = sorted(active, key=lambda p: p["chance"], reverse=True)
    return {"count": len(ranked), "items": ranked}


# --------------------------------------------------------------------------- #
# HTML Dashboard                                                              #
# --------------------------------------------------------------------------- #
ROUND_LABELS = {"group": "Group Stage", "r32": "Round of 32", "r16": "Round of 16",
                "qf": "Quarterfinals", "sf": "Semifinals", "third": "3rd Place", "final": "Final"}


def _clean_scorers(s: str) -> str:
    if not s or s == "null":
        return ""
    return s.replace("{", "").replace("}", "").replace('"', '').replace("\u201c", "").replace("\u201d", "")


def _render_live_results(games: list[dict]) -> str:
    live = [g for g in games if g.get("finished") != "TRUE" and g.get("time_elapsed") not in ("not_started", "notstarted", None, "")]
    finished = [g for g in games if g.get("finished") == "TRUE"]
    upcoming = [g for g in games if g.get("finished") != "TRUE" and g.get("time_elapsed") in ("not_started", "notstarted", None, "")]

    finished.sort(key=lambda g: g.get("local_date", ""), reverse=True)
    upcoming.sort(key=lambda g: g.get("local_date", ""))

    html = ""
    if live:
        html += '<h3 class="section-header live-pulse">LIVE NOW</h3><div class="matches">'
        for g in live:
            html += _match_card(g, "live")
        html += '</div>'

    if upcoming:
        html += '<h3 class="section-header">Today / Upcoming</h3><div class="matches">'
        for g in upcoming[:8]:
            html += _match_card(g, "upcoming")
        html += '</div>'

    if finished:
        html += '<h3 class="section-header">Latest Results</h3><div class="matches">'
        for g in finished[:12]:
            html += _match_card(g, "ft")
        html += '</div>'

    if not (live or finished or upcoming):
        html += '<div class="empty-state"><p>No data — <a href="/api/cron">trigger refresh</a></p></div>'
    return html


def _match_card(g: dict, status_class: str) -> str:
    home = g.get("home_team_name_en") or g.get("home_team_label", "TBD")
    away = g.get("away_team_name_en") or g.get("away_team_label", "TBD")
    hs = g.get("home_score", "-")
    aws = g.get("away_score", "-")
    rtype = g.get("type", "group")
    round_label = ROUND_LABELS.get(rtype, rtype.upper())
    time_el = g.get("time_elapsed", "")
    group = g.get("group", "")
    bjt = _to_beijing_time(g.get("local_date", ""))

    if status_class == "live":
        badge = f"LIVE {time_el}'" if time_el else "LIVE"
    elif status_class == "upcoming":
        badge = "Upcoming"
        hs = ""
        aws = ""
    else:
        badge = "FT"

    score_display = f"{hs} - {aws}" if hs != "" else "vs"
    group_info = f' &middot; Group {group}' if rtype == "group" and group else ""

    scorers = ""
    sh = _clean_scorers(g.get("home_scorers", ""))
    sa = _clean_scorers(g.get("away_scorers", ""))
    if sh:
        scorers += f'<div class="scorers">{sh}</div>'
    if sa:
        scorers += f'<div class="scorers">{sa}</div>'

    return f'''
    <div class="match-card {status_class}">
      <div class="match-meta"><span class="round-label">{round_label}{group_info}</span><span class="status-badge {status_class}">{badge}</span></div>
      <div class="match-teams">
        <div class="team home">{home}</div>
        <div class="score">{score_display}</div>
        <div class="team away">{away}</div>
      </div>
      {scorers}
      <div class="match-date">{bjt}</div>
    </div>'''


def _render_bracket(games: list[dict]) -> str:
    """Render knockout bracket as a structured visual."""
    knockouts = [g for g in games if g.get("type") != "group"]
    knockouts.sort(key=lambda g: int(g.get("id", "0")))

    by_round: dict[str, list] = {}
    for g in knockouts:
        r = g.get("type", "")
        by_round.setdefault(r, []).append(g)

    rounds_order = ["r32", "r16", "qf", "sf", "third", "final"]
    html = '<div class="bracket-container">'

    for rnd in rounds_order:
        matches = by_round.get(rnd, [])
        if not matches:
            continue
        label = ROUND_LABELS.get(rnd, rnd.upper())
        count = len(matches)
        html += f'<div class="bracket-round"><h3 class="bracket-round-title">{label} <span class="match-count">({count} matches)</span></h3><div class="bracket-matches">'

        for g in matches:
            home = g.get("home_team_name_en") or g.get("home_team_label", "TBD")
            away = g.get("away_team_name_en") or g.get("away_team_label", "TBD")
            hs = g.get("home_score", "")
            aws = g.get("away_score", "")
            finished = g.get("finished") == "TRUE"
            is_live = g.get("time_elapsed") not in ("finished", "not_started", "notstarted", None, "") and not finished
            bjt = _to_beijing_time(g.get("local_date", ""))

            if finished:
                state = "ft"
                home_win = hs and aws and int(hs) > int(aws)
                away_win = hs and aws and int(aws) > int(hs)
            elif is_live:
                state = "live"
                home_win = False
                away_win = False
            else:
                state = "upcoming"
                home_win = False
                away_win = False
                hs = ""
                aws = ""

            html += f'''
            <div class="bracket-match {state}">
              <div class="bm-row {'winner' if home_win else ''}"><span class="bm-team">{home}</span><span class="bm-score">{hs}</span></div>
              <div class="bm-row {'winner' if away_win else ''}"><span class="bm-team">{away}</span><span class="bm-score">{aws}</span></div>
              <div class="bm-time">{bjt}</div>
            </div>'''

        html += '</div></div>'
    html += '</div>'
    return html


def _render_predictions_html() -> str:
    # Active teams first (sorted by chance), then eliminated
    active = sorted([p for p in PREDICTIONS if p["chance"] > 0], key=lambda p: p["chance"], reverse=True)
    eliminated = [p for p in PREDICTIONS if p["chance"] == 0]

    html = '<div class="pred-section"><h3 class="section-header">Still in contention</h3><table class="pred-table"><thead><tr><th>#</th><th>Team</th><th>Status</th><th>Title chance</th><th>Analysis</th></tr></thead><tbody>'

    max_chance = active[0]["chance"] if active else 1
    for i, p in enumerate(active):
        bar_w = (p["chance"] / max_chance) * 100
        html += f'''<tr>
          <td class="rank">{i+1}</td>
          <td class="team-cell"><span class="flag">{p["flag"]}</span> {p["team"]}</td>
          <td class="status-cell">{p["status"]}<br><span class="form">{p["form"]}</span></td>
          <td><div class="bar-wrap"><div class="bar" style="width:{bar_w:.0f}%"></div><span class="bar-label">{p["chance"]:.1f}%</span></div></td>
          <td class="reason">{p["reason"]}</td>
        </tr>'''

    html += '</tbody></table></div>'

    # Eliminated section
    html += '<div class="pred-section"><h3 class="section-header elim-header">Eliminated</h3><div class="elim-grid">'
    for p in eliminated:
        html += f'<div class="elim-card"><span class="flag">{p["flag"]}</span> <strong>{p["team"]}</strong><br><span class="elim-status">{p["status"]}</span><br><span class="elim-reason">{p["reason"]}</span></div>'
    html += '</div></div>'
    return html


def render_dashboard() -> str:
    games = _cache["games"]
    last_upd = _cache.get("last_updated") or "never"
    total = len(games)
    finished = sum(1 for g in games if g.get("finished") == "TRUE")
    live = sum(1 for g in games if g.get("finished") != "TRUE" and g.get("time_elapsed") not in ("not_started", "notstarted", None, ""))

    live_html = _render_live_results(games)
    bracket_html = _render_bracket(games)
    predictions_html = _render_predictions_html()

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>World Cup 2026 Tracker</title>
  <style>
    :root {{--bg1:#0b1220;--bg2:#0f2a24;--card:#131b2e;--line:#1f2a44;--text:#e6edf6;--muted:#94a3b8;--accent:#22d3ee;--accent2:#34d399;--gold:#fbbf24;--live:#ef4444;}}
    *{{box-sizing:border-box}}
    html,body{{margin:0;padding:0;background:linear-gradient(160deg,var(--bg1),var(--bg2));color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;min-height:100vh}}
    .wrap{{max-width:1200px;margin:0 auto;padding:24px 16px 60px}}
    header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:24px}}
    .brand{{display:flex;align-items:center;gap:12px}}
    .badge{{width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));display:grid;place-items:center;font-size:20px;font-weight:700;color:#0b1220}}
    h1{{margin:0;font-size:19px}} .sub{{color:var(--muted);font-size:11px}}
    .chips{{display:flex;gap:6px;flex-wrap:wrap;align-items:center}}
    .chip{{background:rgba(255,255,255,.05);border:1px solid var(--line);padding:4px 10px;border-radius:999px;font-size:11px}}
    .chip.live{{background:rgba(239,68,68,.15);border-color:var(--live);color:var(--live);font-weight:600;animation:pulse 2s infinite}}
    @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.6}}}}

    .tabs{{display:flex;gap:4px;margin-bottom:18px;background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:12px;padding:4px;width:fit-content}}
    .tab{{padding:7px 16px;border-radius:9px;font-size:12px;font-weight:500;cursor:pointer;transition:all .15s;color:var(--muted);border:none;background:none}}
    .tab.active{{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#0b1220;font-weight:600;box-shadow:0 2px 8px rgba(34,211,238,.25)}}
    .tab:hover:not(.active){{color:var(--text)}}
    .tab-panel{{display:none}}.tab-panel.active{{display:block}}

    .section-header{{margin:18px 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent2)}}
    .section-header.live-pulse{{color:var(--live);animation:pulse 2s infinite}}
    .matches{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px}}
    .match-card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;transition:border-color .12s}}
    .match-card:hover{{border-color:var(--accent)}}
    .match-card.live{{border-color:var(--live);box-shadow:0 0 10px rgba(239,68,68,.12)}}
    .match-meta{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}}
    .round-label{{font-size:10px;color:var(--muted)}}
    .status-badge{{padding:2px 7px;border-radius:4px;font-size:9px;font-weight:600;text-transform:uppercase}}
    .status-badge.live{{background:var(--live);color:#fff;animation:pulse 2s infinite}}
    .status-badge.ft{{background:rgba(255,255,255,.06);color:var(--muted)}}
    .status-badge.upcoming{{background:rgba(34,211,238,.1);color:var(--accent)}}
    .match-teams{{display:flex;align-items:center;justify-content:space-between;gap:6px;margin:6px 0}}
    .team{{flex:1;font-size:13px;font-weight:500}}.team.away{{text-align:right}}
    .score{{font-size:18px;font-weight:700;min-width:50px;text-align:center;color:var(--accent)}}
    .match-card.live .score{{color:var(--live)}}
    .scorers{{font-size:10px;color:var(--muted);margin:3px 0}}
    .match-date{{font-size:10px;color:var(--muted);margin-top:5px;padding-top:5px;border-top:1px solid var(--line)}}

    /* Bracket */
    .bracket-container{{display:flex;gap:16px;overflow-x:auto;padding-bottom:12px}}
    .bracket-round{{min-width:220px;flex-shrink:0}}
    .bracket-round-title{{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent2);margin:0 0 10px;white-space:nowrap}}
    .match-count{{color:var(--muted);font-weight:400;font-size:10px}}
    .bracket-matches{{display:flex;flex-direction:column;gap:6px}}
    .bracket-match{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:12px}}
    .bracket-match.live{{border-color:var(--live);box-shadow:0 0 8px rgba(239,68,68,.1)}}
    .bracket-match.upcoming{{opacity:.7}}
    .bm-row{{display:flex;justify-content:space-between;padding:2px 0}}
    .bm-row.winner{{color:var(--accent2);font-weight:600}}
    .bm-team{{flex:1}}.bm-score{{font-weight:700;min-width:20px;text-align:right}}
    .bm-time{{font-size:9px;color:var(--muted);margin-top:3px;padding-top:3px;border-top:1px solid var(--line)}}

    /* Predictions */
    .pred-section{{margin-bottom:20px}}
    .pred-table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
    .pred-table th,.pred-table td{{padding:9px 10px;text-align:left;border-bottom:1px solid var(--line);font-size:11px;vertical-align:middle}}
    .pred-table thead th{{background:rgba(255,255,255,.03);font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}}
    .pred-table tr:last-child td{{border-bottom:none}}
    .rank{{font-weight:700;color:var(--gold);width:26px}}
    .team-cell{{font-weight:600;white-space:nowrap}}.flag{{font-size:15px;margin-right:3px}}
    .status-cell{{font-size:10px;color:var(--accent2)}}.form{{color:var(--muted);font-size:9px;letter-spacing:1px}}
    .bar-wrap{{position:relative;background:rgba(255,255,255,.05);border-radius:5px;height:18px;overflow:hidden;min-width:100px}}
    .bar{{background:linear-gradient(90deg,var(--accent2),var(--accent));height:100%}}
    .bar-label{{position:absolute;inset:0;display:grid;place-items:center;font-size:9px;font-weight:700}}
    .reason{{color:#94a3b8;font-size:10px;max-width:300px}}
    .elim-header{{color:var(--muted)}}
    .elim-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}}
    .elim-card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:11px;opacity:.7}}
    .elim-status{{color:var(--live);font-size:10px}}.elim-reason{{color:var(--muted);font-size:10px}}

    .empty-state{{text-align:center;padding:40px;color:var(--muted)}}
    .empty-state a{{color:var(--accent)}}
    .update-note{{font-size:10px;color:var(--muted);margin-top:14px}}
    footer{{margin-top:28px;text-align:center;font-size:10px;color:var(--muted)}} footer a{{color:var(--accent);text-decoration:none}}
  </style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      <div class="badge">WC</div>
      <div><h1>FIFA World Cup 2026 Tracker</h1><div class="sub">USA &middot; Canada &middot; Mexico &middot; All times in Beijing Time (UTC+8)</div></div>
    </div>
    <div class="chips">
      {'<span class="chip live">&#128308; ' + str(live) + ' LIVE</span>' if live > 0 else ''}
      <span class="chip">{finished}/{total} played</span>
      <span class="chip">Round of 16</span>
    </div>
  </header>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('scores')">Live / Results</button>
    <button class="tab" onclick="switchTab('bracket')">Bracket</button>
    <button class="tab" onclick="switchTab('predictions')">Predictions</button>
  </div>

  <div id="tab-scores" class="tab-panel active">
    {live_html}
    <p class="update-note">Last refreshed: {last_upd} &middot; Cron: daily 7am Beijing</p>
  </div>

  <div id="tab-bracket" class="tab-panel">
    <p style="color:var(--muted);font-size:11px;margin-bottom:12px;">Knockout stage bracket &middot; Winners highlighted in green</p>
    {bracket_html}
  </div>

  <div id="tab-predictions" class="tab-panel">
    <p style="color:var(--muted);font-size:11px;margin-bottom:12px;">Updated predictions reflecting actual tournament performance through Round of 16.</p>
    {predictions_html}
  </div>

  <footer>
    <a href="/api">/api</a> &middot; <a href="/api/games">/api/games</a> &middot; <a href="/api/predictions">/api/predictions</a>
    <br>Data: <a href="https://worldcup26.ir">worldcup26.ir</a> &middot; Predictions for entertainment
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
    if not _cache["games"]:
        try:
            refresh_cache()
        except Exception:
            pass
    return HTMLResponse(render_dashboard())
