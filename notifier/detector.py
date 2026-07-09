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
