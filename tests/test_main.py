from unittest.mock import patch, MagicMock
from notifier.main import run_once


def test_run_once_no_events():
    config = {
        "webhook_url": "https://example.com/webhook",
        "api_base_url": "https://worldcup26.ir/get",
        "poll_interval_active": 30,
        "poll_interval_idle": 300,
        "poll_interval_default": 60,
        "timezone": "Asia/Shanghai",
        "tournament_end": "2026-07-20",
        "log_level": "INFO"
    }
    with patch('notifier.main.fetch_games') as mock_fetch, \
         patch('notifier.main.load_state') as mock_load, \
         patch('notifier.main.save_state') as mock_save:

        mock_fetch.return_value = [{
            "id": "73", "home": "Brazil", "away": "Japan",
            "home_score": 1, "away_score": 0,
            "home_scorers": ["Vinicius Jr. 23'"], "away_scorers": [],
            "is_finished": False, "is_live": True,
            "minute": "30", "stage": "16强", "local_date": "07/05/2026 20:00", "type": "r16"
        }]
        mock_load.return_value = {
            "matches": {
                "73": {
                    "home": "Brazil", "away": "Japan",
                    "home_score": 1, "away_score": 0,
                    "status": "in_progress",
                    "events_notified": ["goal_home_1"]
                }
            }
        }

        result = run_once(config, "/tmp/state.json")
        assert result is False
        mock_save.assert_not_called()


def test_run_once_with_goal():
    config = {
        "webhook_url": "https://example.com/webhook",
        "api_base_url": "https://worldcup26.ir/get",
        "poll_interval_active": 30,
        "poll_interval_idle": 300,
        "poll_interval_default": 60,
        "timezone": "Asia/Shanghai",
        "tournament_end": "2026-07-20",
        "log_level": "INFO"
    }
    with patch('notifier.main.fetch_games') as mock_fetch, \
         patch('notifier.main.load_state') as mock_load, \
         patch('notifier.main.save_state') as mock_save, \
         patch('notifier.main.send_notification') as mock_send:

        mock_fetch.return_value = [{
            "id": "73", "home": "Brazil", "away": "Japan",
            "home_score": 2, "away_score": 0,
            "home_scorers": ["Vinicius Jr. 23'", "Endrick 55'"], "away_scorers": [],
            "is_finished": False, "is_live": True,
            "minute": "56", "stage": "16强", "local_date": "07/05/2026 20:00", "type": "r16"
        }]
        mock_load.return_value = {
            "matches": {
                "73": {
                    "home": "Brazil", "away": "Japan",
                    "home_score": 1, "away_score": 0,
                    "status": "in_progress",
                    "events_notified": ["goal_home_1"]
                }
            }
        }
        mock_send.return_value = True

        result = run_once(config, "/tmp/state.json")
        assert result is True
        mock_send.assert_called_once()
        mock_save.assert_called_once()


def test_run_once_send_failure_no_state_save():
    config = {
        "webhook_url": "https://example.com/webhook",
        "api_base_url": "https://worldcup26.ir/get",
        "poll_interval_active": 30,
        "poll_interval_idle": 300,
        "poll_interval_default": 60,
        "timezone": "Asia/Shanghai",
        "tournament_end": "2026-07-20",
        "log_level": "INFO"
    }
    with patch('notifier.main.fetch_games') as mock_fetch, \
         patch('notifier.main.load_state') as mock_load, \
         patch('notifier.main.save_state') as mock_save, \
         patch('notifier.main.send_notification') as mock_send:

        mock_fetch.return_value = [{
            "id": "73", "home": "Brazil", "away": "Japan",
            "home_score": 2, "away_score": 0,
            "home_scorers": ["Vinicius Jr. 23'", "Endrick 55'"], "away_scorers": [],
            "is_finished": False, "is_live": True,
            "minute": "56", "stage": "16强", "local_date": "07/05/2026 20:00", "type": "r16"
        }]
        mock_load.return_value = {
            "matches": {
                "73": {
                    "home": "Brazil", "away": "Japan",
                    "home_score": 1, "away_score": 0,
                    "status": "in_progress",
                    "events_notified": ["goal_home_1"]
                }
            }
        }
        mock_send.return_value = False  # Webhook delivery fails

        result = run_once(config, "/tmp/state.json")
        assert result is False
        mock_save.assert_not_called()  # State NOT saved on failure
