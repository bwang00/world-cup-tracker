"""
FIFA World Cup 2026 Tracker — a tiny FastAPI app for Vercel.

Endpoints
    GET  /              -> HTML dashboard
    GET  /api           -> API metadata
    GET  /api/health    -> health check
    GET  /api/tournament -> tournament summary (dates, hosts, format)
    GET  /api/highlights -> curated highlights & storylines
    GET  /api/predictions -> title-odds predictions with reasoning
    GET  /api/predictions/top?limit=N -> top-N contenders
    GET  /api/teams     -> confirmed / likely qualified teams

Since the 2026 tournament hasn't kicked off yet, "highlights" reflect the
qualification cycle and pre-tournament storylines. Predictions are model-free
heuristic ratings — treat them as opinions, not oracles.
"""

from __future__ import annotations

from datetime import date
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

app = FastAPI(
    title="World Cup 2026 Tracker",
    description="Highlights, predictions and a live dashboard for FIFA World Cup 2026.",
    version="1.0.0",
)


# --------------------------------------------------------------------------- #
# Data                                                                        #
# --------------------------------------------------------------------------- #
TOURNAMENT = {
    "name": "FIFA World Cup 2026",
    "hosts": ["United States", "Canada", "Mexico"],
    "opening_match": "2026-06-11",
    "final": "2026-07-19",
    "final_venue": "MetLife Stadium, New Jersey",
    "teams": 48,
    "groups": 12,
    "format": (
        "First 48-team World Cup. 12 groups of 4 play a round-robin. "
        "Top 2 in each group plus the 8 best third-placed teams advance to a "
        "new Round of 32."
    ),
    "host_cities": 16,
}

HIGHLIGHTS = [
    {
        "date": "2026-06-11",
        "title": "Opening night at the Azteca",
        "detail": (
            "Mexico kicks off the tournament in Mexico City — the Estadio "
            "Azteca becomes the first stadium to host matches at three different "
            "World Cups (1970, 1986, 2026)."
        ),
        "tags": ["ceremony", "history"],
    },
    {
        "date": "2025-11-15",
        "title": "European qualifying wraps",
        "detail": (
            "France, England, Spain, Portugal, Germany, Netherlands, Italy and "
            "Croatia all secure their places, with Norway (Haaland) returning "
            "to the World Cup for the first time since 1998."
        ),
        "tags": ["qualification", "UEFA"],
    },
    {
        "date": "2025-09-10",
        "title": "CONMEBOL locks in six",
        "detail": (
            "Argentina, Brazil, Uruguay, Colombia, Ecuador and Paraguay all "
            "qualify — the reigning champions look sharp with Messi still "
            "leading the line."
        ),
        "tags": ["qualification", "CONMEBOL"],
    },
    {
        "date": "2025-10-14",
        "title": "African giants confirmed",
        "detail": (
            "Morocco, Senegal, Ivory Coast, Egypt, Nigeria, Ghana, Algeria and "
            "Cameroon punch their tickets. Cape Verde emerges as a surprise "
            "first-time qualifier."
        ),
        "tags": ["qualification", "CAF"],
    },
    {
        "date": "2026-06-27",
        "title": "Group stage finale — Round of 32 seeds set",
        "detail": (
            "The final matchday completes 72 group matches. FIFA publishes the "
            "eight best third-placed teams — the most complex tiebreaker "
            "scenario in World Cup history."
        ),
        "tags": ["group stage"],
    },
    {
        "date": "2026-07-19",
        "title": "Final — MetLife Stadium",
        "detail": (
            "The 2026 champion is crowned in New Jersey. First 48-team final "
            "in history."
        ),
        "tags": ["final"],
    },
]

# Heuristic power ratings 0-100 based on recent form, squad depth and pedigree.
# `chance` = rough title-probability estimate (percentage).
PREDICTIONS = [
    {"team": "Argentina", "flag": "AR", "rating": 92, "chance": 15.5,
     "reason": "Reigning champions, elite midfield, Messi legacy plus Julian Alvarez peaking."},
    {"team": "France", "flag": "FR", "rating": 91, "chance": 14.0,
     "reason": "Mbappe at his peak; deepest attacking pool in Europe; finalists in 2018 and 2022."},
    {"team": "Brazil", "flag": "BR", "rating": 89, "chance": 12.0,
     "reason": "New generation (Vinicius, Rodrygo, Endrick) plus Ancelotti's tactical structure."},
    {"team": "England", "flag": "EN", "rating": 87, "chance": 10.5,
     "reason": "Bellingham-Foden-Saka triangle is world-class; keeper depth is the swing factor."},
    {"team": "Spain", "flag": "ES", "rating": 86, "chance": 9.0,
     "reason": "Euro 2024 champions; Yamal and Nico Williams electrify wide play."},
    {"team": "Portugal", "flag": "PT", "rating": 82, "chance": 6.0,
     "reason": "Ronaldo's swan song, but the engine is now Bruno, Vitinha and Bernardo."},
    {"team": "Germany", "flag": "DE", "rating": 81, "chance": 5.5,
     "reason": "Musiala-Wirtz axis plus Kimmich veteran presence; defense still the question."},
    {"team": "Netherlands", "flag": "NL", "rating": 80, "chance": 4.5,
     "reason": "Van Dijk-led defense; Gakpo and Reijnders progression give a balanced side."},
    {"team": "Morocco", "flag": "MA", "rating": 78, "chance": 3.5,
     "reason": "2022 semifinalists; deepest African squad; defense unmatched at AFCON."},
    {"team": "Belgium", "flag": "BE", "rating": 76, "chance": 3.0,
     "reason": "Golden generation faded, but De Bruyne and Doku still make them dangerous."},
    {"team": "Uruguay", "flag": "UY", "rating": 77, "chance": 3.0,
     "reason": "Bielsa's press plus Nunez/Pellistri front line; Copa America form encouraging."},
    {"team": "Italy", "flag": "IT", "rating": 75, "chance": 2.5,
     "reason": "Returning after two missed cycles; midfield strong, striker crisis unresolved."},
    {"team": "United States", "flag": "US", "rating": 73, "chance": 2.5,
     "reason": "Home advantage worth ~5% swing; Pulisic-McKennie-Reyna core in prime."},
    {"team": "Colombia", "flag": "CO", "rating": 74, "chance": 2.0,
     "reason": "James's renaissance and Luis Diaz make them a knockout-round threat."},
    {"team": "Croatia", "flag": "HR", "rating": 72, "chance": 2.0,
     "reason": "Modric winding down but tactical maturity keeps them dangerous."},
    {"team": "Mexico", "flag": "MX", "rating": 70, "chance": 1.5,
     "reason": "Host status, but generational transition still incomplete."},
    {"team": "Japan", "flag": "JP", "rating": 71, "chance": 1.2,
     "reason": "Best Asian side by a distance; Mitoma-Kubo-Kamada trio thrives in Europe."},
    {"team": "Senegal", "flag": "SN", "rating": 70, "chance": 1.0,
     "reason": "Physicality plus Mendy in goal; needs Sarr/Jackson to click up top."},
    {"team": "Denmark", "flag": "DK", "rating": 69, "chance": 0.7,
     "reason": "Hjulmand's structure plus Hojlund/Eriksen give them a puncher's chance."},
    {"team": "Switzerland", "flag": "CH", "rating": 67, "chance": 0.4,
     "reason": "Reliable knockout-round attendee, but ceiling looks like quarterfinals."},
]

TEAMS_CONFIRMED = [
    {"team": "United States", "confederation": "CONCACAF", "status": "host"},
    {"team": "Canada",        "confederation": "CONCACAF", "status": "host"},
    {"team": "Mexico",        "confederation": "CONCACAF", "status": "host"},
    {"team": "France",       "confederation": "UEFA", "status": "qualified"},
    {"team": "England",      "confederation": "UEFA", "status": "qualified"},
    {"team": "Spain",        "confederation": "UEFA", "status": "qualified"},
    {"team": "Portugal",     "confederation": "UEFA", "status": "qualified"},
    {"team": "Germany",      "confederation": "UEFA", "status": "qualified"},
    {"team": "Netherlands",  "confederation": "UEFA", "status": "qualified"},
    {"team": "Italy",        "confederation": "UEFA", "status": "qualified"},
    {"team": "Croatia",      "confederation": "UEFA", "status": "qualified"},
    {"team": "Belgium",      "confederation": "UEFA", "status": "qualified"},
    {"team": "Denmark",      "confederation": "UEFA", "status": "qualified"},
    {"team": "Switzerland",  "confederation": "UEFA", "status": "qualified"},
    {"team": "Norway",       "confederation": "UEFA", "status": "qualified"},
    {"team": "Argentina",    "confederation": "CONMEBOL", "status": "qualified"},
    {"team": "Brazil",       "confederation": "CONMEBOL", "status": "qualified"},
    {"team": "Uruguay",      "confederation": "CONMEBOL", "status": "qualified"},
    {"team": "Colombia",     "confederation": "CONMEBOL", "status": "qualified"},
    {"team": "Ecuador",      "confederation": "CONMEBOL", "status": "qualified"},
    {"team": "Paraguay",     "confederation": "CONMEBOL", "status": "qualified"},
    {"team": "Morocco",      "confederation": "CAF", "status": "qualified"},
    {"team": "Senegal",      "confederation": "CAF", "status": "qualified"},
    {"team": "Ivory Coast",  "confederation": "CAF", "status": "qualified"},
    {"team": "Egypt",        "confederation": "CAF", "status": "qualified"},
    {"team": "Nigeria",      "confederation": "CAF", "status": "qualified"},
    {"team": "Ghana",        "confederation": "CAF", "status": "qualified"},
    {"team": "Japan",        "confederation": "AFC", "status": "qualified"},
    {"team": "South Korea",  "confederation": "AFC", "status": "qualified"},
    {"team": "Iran",         "confederation": "AFC", "status": "qualified"},
    {"team": "Australia",    "confederation": "AFC", "status": "qualified"},
    {"team": "Saudi Arabia", "confederation": "AFC", "status": "qualified"},
]


# --------------------------------------------------------------------------- #
# API routes                                                                  #
# --------------------------------------------------------------------------- #
@app.get("/api")
def api_root():
    days = (date(2026, 6, 11) - date.today()).days
    return {
        "name": "World Cup 2026 Tracker",
        "version": "1.0.0",
        "days_until_kickoff": days,
        "endpoints": [
            "/api/health",
            "/api/tournament",
            "/api/highlights",
            "/api/predictions",
            "/api/predictions/top?limit=5",
            "/api/teams",
        ],
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/tournament")
def tournament():
    days = (date(2026, 6, 11) - date.today()).days
    return {**TOURNAMENT, "days_until_kickoff": days}


@app.get("/api/highlights")
def highlights():
    return {"count": len(HIGHLIGHTS), "items": HIGHLIGHTS}


@app.get("/api/predictions")
def predictions():
    ranked = sorted(PREDICTIONS, key=lambda p: p["chance"], reverse=True)
    return {"count": len(ranked), "items": ranked}


@app.get("/api/predictions/top")
def predictions_top(limit: int = Query(5, ge=1, le=20)):
    ranked = sorted(PREDICTIONS, key=lambda p: p["chance"], reverse=True)[:limit]
    return {"count": len(ranked), "items": ranked}


@app.get("/api/teams")
def teams():
    by_conf: dict[str, list] = {}
    for t in TEAMS_CONFIRMED:
        by_conf.setdefault(t["confederation"], []).append(t)
    return {"count": len(TEAMS_CONFIRMED), "by_confederation": by_conf}


# --------------------------------------------------------------------------- #
# HTML dashboard                                                              #
# --------------------------------------------------------------------------- #
def render_dashboard() -> str:
    days = (date(2026, 6, 11) - date.today()).days
    top5 = sorted(PREDICTIONS, key=lambda p: p["chance"], reverse=True)[:5]

    highlight_cards = "".join(
        f"""
        <article class="card">
          <div class="card-date">{h['date']}</div>
          <h3>{h['title']}</h3>
          <p>{h['detail']}</p>
          <div class="tags">{''.join(f'<span class="tag">{t}</span>' for t in h['tags'])}</div>
        </article>
        """
        for h in HIGHLIGHTS
    )

    max_chance = max(p["chance"] for p in top5)
    prediction_rows = "".join(
        f"""
        <tr>
          <td class="rank">{i+1}</td>
          <td class="team">{p['team']} <span class="cc">({p['flag']})</span></td>
          <td>
            <div class="bar-wrap">
              <div class="bar" style="width:{(p['chance']/max_chance)*100:.0f}%"></div>
              <span class="bar-label">{p['chance']:.1f}%</span>
            </div>
          </td>
          <td class="reason">{p['reason']}</td>
        </tr>
        """
        for i, p in enumerate(top5)
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>World Cup 2026 Tracker</title>
  <style>
    :root {{
      --bg1:#0b1220; --bg2:#0f2a24; --card:#131b2e; --line:#1f2a44;
      --text:#e6edf6; --muted:#94a3b8; --accent:#22d3ee; --accent2:#34d399;
      --gold:#fbbf24;
    }}
    *{{box-sizing:border-box}}
    html,body{{margin:0;padding:0;background:linear-gradient(160deg,var(--bg1),var(--bg2));color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;min-height:100vh}}
    .wrap{{max-width:1080px;margin:0 auto;padding:32px 24px 80px}}
    header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;margin-bottom:32px}}
    .brand{{display:flex;align-items:center;gap:14px}}
    .badge{{width:52px;height:52px;border-radius:16px;background:linear-gradient(135deg,var(--accent),var(--accent2));display:grid;place-items:center;font-size:26px}}
    h1{{margin:0;font-size:22px;letter-spacing:-.01em}}
    .sub{{color:var(--muted);font-size:13px}}
    .chips{{display:flex;gap:8px;flex-wrap:wrap}}
    .chip{{background:rgba(255,255,255,.05);border:1px solid var(--line);color:var(--text);padding:6px 12px;border-radius:999px;font-size:12px}}
    .countdown{{background:linear-gradient(135deg,#fbbf24,#f97316);color:#1a0f00;padding:6px 14px;border-radius:999px;font-weight:700;font-size:12px}}
    h2{{margin:32px 0 12px;font-size:16px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}}
    .card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;transition:transform .12s ease,border-color .12s ease}}
    .card:hover{{transform:translateY(-2px);border-color:var(--accent)}}
    .card-date{{font-size:11px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px}}
    .card h3{{margin:0 0 6px;font-size:15px}}
    .card p{{margin:0 0 10px;color:#cbd5e1;font-size:13px;line-height:1.5}}
    .tags{{display:flex;flex-wrap:wrap;gap:4px}}
    .tag{{font-size:10px;color:var(--accent);background:rgba(34,211,238,.08);border:1px solid rgba(34,211,238,.25);padding:2px 8px;border-radius:6px}}
    table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}}
    th,td{{padding:12px 14px;text-align:left;border-bottom:1px solid var(--line);font-size:13px;vertical-align:middle}}
    th{{background:rgba(255,255,255,.03);font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}}
    tr:last-child td{{border-bottom:none}}
    .rank{{font-weight:700;color:var(--gold);width:36px}}
    .team{{font-weight:600;white-space:nowrap}}
    .cc{{color:var(--muted);font-weight:400;font-size:11px}}
    .bar-wrap{{position:relative;background:rgba(255,255,255,.05);border-radius:6px;height:22px;overflow:hidden;min-width:140px}}
    .bar{{background:linear-gradient(90deg,var(--accent2),var(--accent));height:100%}}
    .bar-label{{position:absolute;inset:0;display:grid;place-items:center;font-size:11px;font-weight:700}}
    .reason{{color:#94a3b8;font-size:12px;max-width:380px}}
    .api-box{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:#cbd5e1}}
    .api-box a{{color:var(--accent);text-decoration:none;display:block;padding:4px 0}}
    .api-box a:hover{{color:var(--accent2)}}
    footer{{margin-top:36px;color:var(--muted);font-size:11px;text-align:center}}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">
        <div class="badge">WC</div>
        <div>
          <h1>FIFA World Cup 2026 Tracker</h1>
          <div class="sub">USA · Canada · Mexico  ·  June 11 – July 19, 2026</div>
        </div>
      </div>
      <div class="chips">
        <span class="countdown">{days} days to kickoff</span>
        <span class="chip">48 teams</span>
        <span class="chip">12 groups</span>
        <span class="chip">16 host cities</span>
      </div>
    </header>

    <h2>Highlights &amp; Storylines</h2>
    <div class="grid">
      {highlight_cards}
    </div>

    <h2>Top 5 Title Predictions</h2>
    <table>
      <thead>
        <tr><th>#</th><th>Team</th><th>Title chance</th><th>Why</th></tr>
      </thead>
      <tbody>
        {prediction_rows}
      </tbody>
    </table>

    <h2>API Endpoints</h2>
    <div class="api-box">
      <a href="/api">/api</a>
      <a href="/api/tournament">/api/tournament</a>
      <a href="/api/highlights">/api/highlights</a>
      <a href="/api/predictions">/api/predictions</a>
      <a href="/api/predictions/top?limit=5">/api/predictions/top?limit=5</a>
      <a href="/api/teams">/api/teams</a>
    </div>

    <footer>Predictions are heuristic ratings for entertainment. Qualification list will evolve.</footer>
  </div>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
@app.get("/api/dashboard", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(render_dashboard())
