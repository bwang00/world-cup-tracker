import json
from unittest.mock import patch, MagicMock
from notifier.sender import format_goal_message, format_match_finished_message, send_notification


def test_format_goal_message_home():
    event = {
        "type": "goal",
        "match_id": "73",
        "side": "home",
        "goal_number": 2,
        "match": {
            "id": "73", "home": "Brazil", "away": "Japan",
            "home_score": 2, "away_score": 1,
            "home_scorers": ["Vinicius Jr. 23'", "Endrick 55'"],
            "away_scorers": ["Mitoma 45'"],
            "is_finished": False, "is_live": True,
            "minute": "55", "stage": "16强",
            "local_date": "07/05/2026 20:00", "type": "r16"
        }
    }
    msg = format_goal_message(event)
    assert "进球" in msg
    assert "Brazil" in msg
    assert "2 - 1" in msg
    assert "Japan" in msg
    assert "Endrick 55'" in msg
    assert "16强" in msg


def test_format_goal_message_no_scorer_detail():
    """When scorer list doesn't have enough entries, omit player name."""
    event = {
        "type": "goal",
        "match_id": "73",
        "side": "home",
        "goal_number": 3,
        "match": {
            "id": "73", "home": "Brazil", "away": "Japan",
            "home_score": 3, "away_score": 0,
            "home_scorers": ["Vinicius Jr. 23'"],  # Only 1 scorer listed but 3 goals
            "away_scorers": [],
            "is_finished": False, "is_live": True,
            "minute": "70", "stage": "16强",
            "local_date": "07/05/2026 20:00", "type": "r16"
        }
    }
    msg = format_goal_message(event)
    assert "Brazil" in msg
    assert "3 - 0" in msg


def test_format_match_finished_message():
    event = {
        "type": "match_finished",
        "match_id": "73",
        "match": {
            "id": "73", "home": "Brazil", "away": "Japan",
            "home_score": 3, "away_score": 1,
            "home_scorers": ["Vinicius Jr. 23'", "Vinicius Jr. 62'", "Endrick 78'"],
            "away_scorers": ["Mitoma 45'"],
            "is_finished": True, "is_live": False,
            "minute": None, "stage": "16强",
            "local_date": "07/05/2026 20:00", "type": "r16"
        }
    }
    msg = format_match_finished_message(event)
    assert "比赛结束" in msg
    assert "Brazil" in msg
    assert "3 - 1" in msg
    assert "Vinicius Jr." in msg
    assert "Mitoma 45'" in msg
    assert "16强" in msg


def test_format_match_finished_no_scorers():
    event = {
        "type": "match_finished",
        "match_id": "73",
        "match": {
            "id": "73", "home": "Brazil", "away": "Japan",
            "home_score": 0, "away_score": 0,
            "home_scorers": [], "away_scorers": [],
            "is_finished": True, "is_live": False,
            "minute": None, "stage": "小组赛",
            "local_date": "06/15/2026 20:00", "type": "group"
        }
    }
    msg = format_match_finished_message(event)
    assert "比赛结束" in msg
    assert "0 - 0" in msg


def test_send_notification_success():
    with patch('notifier.sender.urllib.request.urlopen') as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"errcode":0}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = send_notification("https://example.com/webhook", "test message")
        assert result is True


def test_send_notification_failure():
    with patch('notifier.sender.urllib.request.urlopen') as mock_urlopen:
        mock_urlopen.side_effect = Exception("Connection refused")
        result = send_notification("https://example.com/webhook", "test message")
        assert result is False
