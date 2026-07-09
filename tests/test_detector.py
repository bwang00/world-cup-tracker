from notifier.detector import detect_changes


def test_no_changes():
    matches = [{
        "id": "73", "home": "Brazil", "away": "Japan",
        "home_score": 1, "away_score": 0,
        "home_scorers": ["Vinicius Jr. 23'"], "away_scorers": [],
        "is_finished": False, "is_live": True,
        "minute": "30", "stage": "16强", "local_date": "07/05/2026 20:00", "type": "r16"
    }]
    state = {
        "matches": {
            "73": {
                "home": "Brazil", "away": "Japan",
                "home_score": 1, "away_score": 0,
                "status": "in_progress",
                "events_notified": ["goal_home_1"]
            }
        }
    }
    events, new_state = detect_changes(matches, state)
    assert events == []
    assert new_state["matches"]["73"]["home_score"] == 1


def test_goal_detected():
    matches = [{
        "id": "73", "home": "Brazil", "away": "Japan",
        "home_score": 2, "away_score": 0,
        "home_scorers": ["Vinicius Jr. 23'", "Endrick 55'"], "away_scorers": [],
        "is_finished": False, "is_live": True,
        "minute": "56", "stage": "16强", "local_date": "07/05/2026 20:00", "type": "r16"
    }]
    state = {
        "matches": {
            "73": {
                "home": "Brazil", "away": "Japan",
                "home_score": 1, "away_score": 0,
                "status": "in_progress",
                "events_notified": ["goal_home_1"]
            }
        }
    }
    events, new_state = detect_changes(matches, state)
    assert len(events) == 1
    assert events[0]["type"] == "goal"
    assert events[0]["match_id"] == "73"
    assert events[0]["side"] == "home"
    assert events[0]["goal_number"] == 2
    assert "goal_home_2" in new_state["matches"]["73"]["events_notified"]


def test_away_goal_has_side_and_number():
    """Away goal events must include side='away' and correct goal_number for sender compat."""
    matches = [{
        "id": "73", "home": "Brazil", "away": "Japan",
        "home_score": 1, "away_score": 1,
        "home_scorers": ["Vinicius Jr. 23'"], "away_scorers": ["Mitoma 45'"],
        "is_finished": False, "is_live": True,
        "minute": "46", "stage": "16强", "local_date": "07/05/2026 20:00", "type": "r16"
    }]
    state = {
        "matches": {
            "73": {
                "home": "Brazil", "away": "Japan",
                "home_score": 1, "away_score": 0,
                "status": "in_progress",
                "events_notified": ["goal_home_1"]
            }
        }
    }
    events, new_state = detect_changes(matches, state)
    assert len(events) == 1
    assert events[0]["type"] == "goal"
    assert events[0]["side"] == "away"
    assert events[0]["goal_number"] == 1
    assert "goal_away_1" in new_state["matches"]["73"]["events_notified"]


def test_match_finished_detected():
    matches = [{
        "id": "73", "home": "Brazil", "away": "Japan",
        "home_score": 2, "away_score": 1,
        "home_scorers": ["Vinicius Jr. 23'", "Endrick 55'"],
        "away_scorers": ["Mitoma 45'"],
        "is_finished": True, "is_live": False,
        "minute": None, "stage": "16强", "local_date": "07/05/2026 20:00", "type": "r16"
    }]
    state = {
        "matches": {
            "73": {
                "home": "Brazil", "away": "Japan",
                "home_score": 2, "away_score": 1,
                "status": "in_progress",
                "events_notified": ["goal_home_1", "goal_home_2", "goal_away_1"]
            }
        }
    }
    events, new_state = detect_changes(matches, state)
    assert len(events) == 1
    assert events[0]["type"] == "match_finished"
    assert new_state["matches"]["73"]["status"] == "finished"


def test_cold_start_no_spurious_notifications():
    """New match appearing should NOT trigger notifications."""
    matches = [{
        "id": "99", "home": "Argentina", "away": "Germany",
        "home_score": 3, "away_score": 1,
        "home_scorers": ["Messi 10'", "Messi 45'", "Alvarez 70'"],
        "away_scorers": ["Müller 30'"],
        "is_finished": False, "is_live": True,
        "minute": "75", "stage": "决赛", "local_date": "07/19/2026 20:00", "type": "final"
    }]
    state = {"matches": {}}
    events, new_state = detect_changes(matches, state)
    assert events == []
    # But state should be initialized
    assert new_state["matches"]["99"]["home_score"] == 3
    assert "goal_home_1" in new_state["matches"]["99"]["events_notified"]
    assert "goal_home_2" in new_state["matches"]["99"]["events_notified"]
    assert "goal_home_3" in new_state["matches"]["99"]["events_notified"]
    assert "goal_away_1" in new_state["matches"]["99"]["events_notified"]


def test_multiple_goals_same_cycle():
    """Two goals scored between polls (e.g., 60s gap)."""
    matches = [{
        "id": "73", "home": "Brazil", "away": "Japan",
        "home_score": 3, "away_score": 0,
        "home_scorers": ["Vinicius Jr. 23'", "Endrick 55'", "Rodrygo 58'"],
        "away_scorers": [],
        "is_finished": False, "is_live": True,
        "minute": "60", "stage": "16强", "local_date": "07/05/2026 20:00", "type": "r16"
    }]
    state = {
        "matches": {
            "73": {
                "home": "Brazil", "away": "Japan",
                "home_score": 1, "away_score": 0,
                "status": "in_progress",
                "events_notified": ["goal_home_1"]
            }
        }
    }
    events, new_state = detect_changes(matches, state)
    assert len(events) == 2
    assert all(e["type"] == "goal" for e in events)


def test_not_started_match_ignored():
    """Matches that haven't started don't generate events."""
    matches = [{
        "id": "100", "home": "Spain", "away": "Belgium",
        "home_score": 0, "away_score": 0,
        "home_scorers": [], "away_scorers": [],
        "is_finished": False, "is_live": False,
        "minute": None, "stage": "8强", "local_date": "07/10/2026 12:00", "type": "qf"
    }]
    state = {"matches": {}}
    events, new_state = detect_changes(matches, state)
    assert events == []
