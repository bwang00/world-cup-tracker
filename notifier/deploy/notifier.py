#!/usr/bin/env python3
"""World Cup Match Notifier - ServerChan Push Service.

Combined single-file deployment. Source: ~/projects/world-cup-tracker/notifier/
"""

# === notifier/config.py ===
import json


def load_config(path: str) -> dict:
    """Load and return configuration from a JSON file.

    Raises FileNotFoundError if the file does not exist.
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

# === notifier/state.py ===
import json
import os
import tempfile
import logging

logger = logging.getLogger(__name__)


def load_state(path: str) -> dict:
    """Load state from JSON file. Returns empty state if file missing or corrupt."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logger.warning("Could not load state from %s: %s. Starting fresh.", path, e)
        return {"matches": {}}


def save_state(path: str, state: dict) -> None:
    """Atomically save state to JSON file (write to temp, then rename)."""
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file if rename failed
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

# === notifier/api.py ===
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

# === notifier/detector.py ===
"""Change detector: compares fresh match data against stored state to emit events."""

import copy
import logging

logger = logging.getLogger(__name__)


def detect_changes(matches: list, state: dict) -> tuple:
    """Compare fresh match data against stored state, return events and updated state.

    Returns:
        (events, new_state) where:
        - events: list of {"type": "goal"|"match_finished", "match_id": str, "match": dict, ...}
        - new_state: updated state dict (only persist this after notifications succeed)
    """
    new_state = copy.deepcopy(state)
    if "matches" not in new_state:
        new_state["matches"] = {}

    events = []

    for match in matches:
        match_id = match["id"]
        home_score = match["home_score"]
        away_score = match["away_score"]
        is_finished = match["is_finished"]
        is_live = match["is_live"]

        # Skip matches that haven't started and have no score
        if not is_live and not is_finished and home_score == 0 and away_score == 0:
            continue

        if match_id not in new_state["matches"]:
            # Cold start: initialize without firing notifications
            logger.info(
                "New match %s detected (cold start): %s %d - %d %s",
                match_id, match["home"], home_score, away_score, match["away"],
            )
            new_state["matches"][match_id] = {
                "home": match["home"],
                "away": match["away"],
                "home_score": home_score,
                "away_score": away_score,
                "status": "finished" if is_finished else "in_progress",
                "events_notified": _generate_existing_event_ids(home_score, away_score, is_finished),
            }
            continue

        stored = new_state["matches"][match_id]
        old_home = stored.get("home_score", 0)
        old_away = stored.get("away_score", 0)
        notified = stored.get("events_notified", [])

        # Detect home goals
        if home_score > old_home:
            for goal_num in range(old_home + 1, home_score + 1):
                event_id = f"goal_home_{goal_num}"
                if event_id not in notified:
                    events.append({
                        "type": "goal",
                        "match_id": match_id,
                        "match": match,
                        "side": "home",
                        "goal_number": goal_num,
                        "detail": f"{match['home']} goal! ({home_score}-{away_score})",
                    })
                    notified.append(event_id)

        # Detect away goals
        if away_score > old_away:
            for goal_num in range(old_away + 1, away_score + 1):
                event_id = f"goal_away_{goal_num}"
                if event_id not in notified:
                    events.append({
                        "type": "goal",
                        "match_id": match_id,
                        "match": match,
                        "side": "away",
                        "goal_number": goal_num,
                        "detail": f"{match['away']} goal! ({home_score}-{away_score})",
                    })
                    notified.append(event_id)

        # Detect match finished
        if is_finished and stored.get("status") != "finished":
            event_id = "match_finished"
            if event_id not in notified:
                events.append({
                    "type": "match_finished",
                    "match_id": match_id,
                    "match": match,
                    "detail": f"Full time: {match['home']} {home_score} - {away_score} {match['away']}",
                })
                notified.append(event_id)

        # Update stored state
        stored["home_score"] = home_score
        stored["away_score"] = away_score
        stored["status"] = "finished" if is_finished else "in_progress"
        stored["events_notified"] = notified

    return events, new_state


def _generate_existing_event_ids(home_score: int, away_score: int, is_finished: bool) -> list:
    """Generate event IDs for an already-in-progress match (cold start).

    This prevents spurious notifications when the bot first sees a match
    that already has goals scored.
    """
    ids = []
    for i in range(1, home_score + 1):
        ids.append(f"goal_home_{i}")
    for i in range(1, away_score + 1):
        ids.append(f"goal_away_{i}")
    if is_finished:
        ids.append("match_finished")
    return ids

# === notifier/sender.py ===
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


def _convert_to_beijing_time(local_date: str) -> str:
    """Convert US Eastern time string 'MM/DD/YYYY HH:MM' to Beijing time 'HH:MM'.

    US Eastern is UTC-4 (EDT) during summer. Beijing is UTC+8. Difference: +12 hours.
    """
    if not local_date:
        return ""
    try:
        parts = local_date.split(" ")
        if len(parts) != 2:
            return local_date
        time_part = parts[1]
        hour, minute = map(int, time_part.split(":"))
        # EDT (UTC-4) to CST (UTC+8) = +12 hours
        beijing_hour = (hour + 12) % 24
        return f"{beijing_hour:02d}:{minute:02d}"
    except (ValueError, IndexError):
        return local_date


def format_goal_message(event: dict) -> str:
    """Format a goal event into a markdown notification message."""
    match = event["match"]
    side = event.get("side", "home")
    goal_number = event.get("goal_number", 1)

    home = match["home"]
    away = match["away"]
    home_score = match["home_score"]
    away_score = match["away_score"]
    minute = match.get("minute", "")
    stage = match.get("stage", "")
    local_date = match.get("local_date", "")
    beijing_time = _convert_to_beijing_time(local_date)

    # Try to find the scorer
    scorers = match.get(f"{side}_scorers", [])
    scorer_line = ""
    if goal_number <= len(scorers):
        scorer = scorers[goal_number - 1]
        scorer_line = f"\n🔥 {scorer}"

    minute_str = f" ({minute}')" if minute else ""
    match_id = match["id"]

    msg = f"⚽ 进球！\n{home} {home_score} - {away_score} {away}{minute_str}"
    if scorer_line:
        msg += scorer_line
    msg += f"\n📺 第{match_id}场 · {stage} · 北京时间 {beijing_time}"

    return msg


def format_match_finished_message(event: dict) -> str:
    """Format a match-finished event into a markdown notification message."""
    match = event["match"]

    home = match["home"]
    away = match["away"]
    home_score = match["home_score"]
    away_score = match["away_score"]
    stage = match.get("stage", "")
    home_scorers = match.get("home_scorers", [])
    away_scorers = match.get("away_scorers", [])

    msg = f"🏁 比赛结束\n{home} {home_score} - {away_score} {away}"

    # Add scorer details if available
    all_scorers = []
    for s in home_scorers:
        all_scorers.append(f"  • {s}")
    for s in away_scorers:
        all_scorers.append(f"  • {s}")

    if all_scorers:
        msg += "\n\n⚽ 进球记录：\n" + "\n".join(all_scorers)

    # Determine advancement info for knockout matches
    advancement = ""
    if match.get("type") in ("r32", "r16", "qf", "sf", "final", "third"):
        draw_label = "平局"
        if home_score > away_score:
            winner = home
        elif away_score > home_score:
            winner = away
        else:
            winner = draw_label
        if winner != draw_label:
            next_stage_map = {
                "r32": "晋级16强", "r16": "晋级8强", "qf": "晋级半决赛",
                "sf": "晋级决赛", "final": "夺冠🏆", "third": "获得季军"
            }
            match_type = match["type"]
            next_txt = next_stage_map.get(match_type, "晋级")
            advancement = f" · {winner}{next_txt}"

    msg += f"\n\n📊 {stage}{advancement}"

    return msg


def send_notification(sendkey: str, message: str) -> bool:
    """Send a notification via Server酱 (ServerChan).

    Args:
        sendkey: The ServerChan SendKey (e.g. 'SCT376902T...')
        message: The message body in markdown format.

    Returns True if delivery succeeded, False otherwise.
    """
    # Extract first line as title (strip emoji prefix)
    title = message.split("\n")[0].strip()
    if len(title) > 32:
        title = title[:32]

    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    payload = urllib.parse.urlencode({
        "title": title,
        "desp": message
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode('utf-8')
            result = json.loads(body)
            if result.get("code") == 0:
                logger.debug("ServerChan response: %s", body)
                return True
            else:
                logger.error("ServerChan error: %s", body)
                return False
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, Exception) as e:
        logger.error("Failed to send notification: %s", e)
        return False

# === notifier/main.py ===
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta


logger = logging.getLogger("wc-notifier")

BEIJING_TZ = timezone(timedelta(hours=8))


def run_once(config: dict, state_path: str) -> bool:
    """Execute a single poll cycle.

    Returns True if events were detected AND notifications sent successfully.
    Returns False if no events, or if notification delivery failed.
    """
    state = load_state(state_path)
    matches = fetch_games(config["api_base_url"])
    events, new_state = detect_changes(matches, state)

    if not events:
        return False

    # Format and send all notifications
    all_sent = True
    for event in events:
        if event["type"] == "goal":
            message = format_goal_message(event)
        elif event["type"] == "match_finished":
            message = format_match_finished_message(event)
        else:
            continue

        success = send_notification(config["sendkey"], message)
        if not success:
            all_sent = False
            logger.error("Failed to send notification for event: %s", event["type"])
            break  # Stop processing — don't save state

    if all_sent:
        new_state["last_check"] = datetime.now(BEIJING_TZ).isoformat()
        save_state(state_path, new_state)
        logger.info("Processed %d event(s) successfully", len(events))
        return True
    else:
        logger.warning("Notification delivery failed, state NOT updated. Will retry.")
        return False


def _get_poll_interval(config: dict, state: dict, matches: list) -> int:
    """Determine next poll interval based on match activity."""
    # Check if any match is currently live
    has_live = any(m.get("is_live") for m in matches)
    if has_live:
        return config.get("poll_interval_active", 30)

    # Check if any match today is not yet finished (upcoming)
    today = datetime.now(BEIJING_TZ).strftime("%m/%d/%Y")
    # local_date is US Eastern — approximate: today's matches in ET
    has_today = any(not m.get("is_finished") for m in matches
                    if m.get("local_date", "").startswith(today[:5]))

    if has_today:
        return config.get("poll_interval_default", 60)

    return config.get("poll_interval_idle", 300)


def _is_tournament_over(config: dict) -> bool:
    """Check if tournament end date has passed."""
    end_str = config.get("tournament_end", "2026-07-20")
    try:
        end_date = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
        return datetime.now(BEIJING_TZ) > end_date
    except ValueError:
        return False


def main():
    """Main entry point: load config and run polling loop."""
    base_dir = os.path.expanduser("~/.wc-notifier")
    config_path = os.path.join(base_dir, "config.json")
    state_path = os.path.join(base_dir, "state.json")

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    try:
        config = load_config(config_path)
    except FileNotFoundError:
        logger.error("Config file not found at %s. Please create it.", config_path)
        sys.exit(1)

    log_level = config.get("log_level", "INFO").upper()
    logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

    logger.info("WC Notifier started. Polling %s", config["api_base_url"])

    consecutive_failures = 0
    last_matches = []

    while True:
        if _is_tournament_over(config):
            logger.info("Tournament has ended. Exiting.")
            break

        try:
            matches = fetch_games(config["api_base_url"])
            last_matches = matches
            consecutive_failures = 0

            run_once(config, state_path)

        except APIError as e:
            consecutive_failures += 1
            logger.warning("API error (attempt %d): %s", consecutive_failures, e)

            if consecutive_failures > 10:
                # Try to send self-diagnosis alert
                send_notification(
                    config["sendkey"],
                    "⚠️ 通知服务异常\n\n世界杯通知服务已连续失败 %d 次，最近错误：%s" % (
                        consecutive_failures, str(e)[:100]
                    )
                )

        except Exception as e:
            consecutive_failures += 1
            logger.exception("Unexpected error (attempt %d): %s", consecutive_failures, e)

        interval = _get_poll_interval(config, load_state(state_path), last_matches)
        logger.debug("Sleeping %d seconds", interval)
        time.sleep(interval)


if __name__ == "__main__":
    main()
