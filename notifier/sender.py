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
    """Format a goal event into a WeCom markdown message."""
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
    """Format a match-finished event into a WeCom markdown message."""
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
