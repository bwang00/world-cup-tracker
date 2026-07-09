import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta

from notifier.config import load_config
from notifier.state import load_state, save_state
from notifier.api import fetch_games, APIError
from notifier.detector import detect_changes
from notifier.sender import format_goal_message, format_match_finished_message, send_notification

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

        success = send_notification(config["webhook_url"], message)
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
                    config["webhook_url"],
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
