# World Cup 2026 Tracker

A small FastAPI service deployed on Vercel that tracks FIFA World Cup 2026 highlights and title predictions.

Live: https://world-cup-tracker-peach.vercel.app

## Endpoints

- `GET /` — HTML dashboard (highlights + top-5 predictions + countdown)
- `GET /api` — API metadata
- `GET /api/health` — health check
- `GET /api/tournament` — tournament summary
- `GET /api/highlights` — curated storylines
- `GET /api/predictions` — full title-chance ranking
- `GET /api/predictions/top?limit=N` — top-N contenders
- `GET /api/teams` — qualified/host teams grouped by confederation

## Local run

```
pip install -r requirements.txt
uvicorn api.index:app --reload
```

## Deploy

```
vercel deploy --prod --yes
```
