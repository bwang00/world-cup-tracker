"""API client for worldcup26.ir match data."""

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Raised when the worldcup26.ir API is unreachable or returns bad data."""
    pass


def parse_scorers(scorers_str: str) -> list:
    """Parse PostgreSQL-style array string into list of scorer strings.

    Input format: {"Player 10'","Player 20'"} or "null" or ""
    Returns: ["Player 10'", "Player 20'"] or []
    """
    if not scorers_str or scorers_str == "null":
        return []

    # Remove outer braces
    s = scorers_str.strip()
    if s.startswith('{') and s.endswith('}'):
        s = s[1:-1]
    else:
        return []

    if not s:
        return []

    # Parse quoted CSV: each entry is wrapped in "..."
    # Handle: "Player 10'","Player 20'"
    entries = []
    current = []
    in_quotes = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '"' and not in_quotes:
            in_quotes = True
        elif ch == '"' and in_quotes:
            in_quotes = False
        elif ch == ',' and not in_quotes:
            entries.append(''.join(current))
            current = []
            i += 1
            continue
        else:
            current.append(ch)
        i += 1

    if current:
        entries.append(''.join(current))

    return [e for e in entries if e]


def parse_match(raw: dict) -> dict:
    """Normalize a raw API match dict into a clean typed dict."""
    home_score_str = raw.get("home_score", "null")
    away_score_str = raw.get("away_score", "null")
    home_score = int(home_score_str) if home_score_str not in ("null", "", None) else 0
    away_score = int(away_score_str) if away_score_str not in ("null", "", None) else 0

    finished = raw.get("finished", "FALSE") == "TRUE"
    time_elapsed = raw.get("time_elapsed", "notstarted")
    is_live = (not finished) and time_elapsed not in ("notstarted", "finished", "null", "")

    # Determine minute
    minute = raw.get("match_minute", "null")
    if minute in ("null", "", None):
        minute = time_elapsed if is_live else None

    match_type = raw.get("type", "group")

    return {
        "id": raw.get("id", ""),
        "home": raw.get("home_team_name_en", ""),
        "away": raw.get("away_team_name_en", ""),
        "home_score": home_score,
        "away_score": away_score,
        "home_scorers": parse_scorers(raw.get("home_scorers", "null")),
        "away_scorers": parse_scorers(raw.get("away_scorers", "null")),
        "is_finished": finished,
        "is_live": is_live,
        "minute": minute,
        "stage": match_type,
        "local_date": raw.get("local_date", ""),
        "type": match_type,
    }


def fetch_games(api_base_url: str) -> list:
    """Fetch all games from worldcup26.ir API.

    Returns list of parsed match dicts.
    Raises APIError on network failure or invalid response.
    """
    url = f"{api_base_url}/games"
    logger.debug("Fetching games from %s", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wc-notifier/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        raise APIError(f"Failed to fetch games from {url}: {e}")
    except json.JSONDecodeError as e:
        raise APIError(f"Invalid JSON response from {url}: {e}")

    # API returns {"games": [...]}
    raw_games = data.get("games", data) if isinstance(data, dict) else data
    if not isinstance(raw_games, list):
        raise APIError(f"Unexpected response structure from {url}")

    logger.info("Fetched %d games from API", len(raw_games))
    return [parse_match(g) for g in raw_games]
