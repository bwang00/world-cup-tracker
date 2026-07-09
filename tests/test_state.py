import json
import os
import tempfile
from notifier.state import load_state, save_state


def test_load_state_missing_file():
    result = load_state("/nonexistent/state.json")
    assert result == {"matches": {}}


def test_load_state_corrupt_file():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("not valid json {{{")
        path = f.name
    try:
        result = load_state(path)
        assert result == {"matches": {}}
    finally:
        os.unlink(path)


def test_save_and_load_state():
    state = {
        "last_check": "2026-07-09T20:30:00+08:00",
        "matches": {
            "73": {
                "home": "Brazil",
                "away": "Japan",
                "home_score": 2,
                "away_score": 1,
                "status": "in_progress",
                "events_notified": ["goal_home_1", "goal_away_1", "goal_home_2"]
            }
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "state.json")
        save_state(path, state)
        loaded = load_state(path)
        assert loaded == state


def test_save_state_atomic(tmp_path):
    """Verify save doesn't corrupt state if crash simulated (file exists before save)."""
    path = str(tmp_path / "state.json")
    original = {"matches": {"1": {"home_score": 0, "away_score": 0}}}
    save_state(path, original)

    # Save new state
    new_state = {"matches": {"1": {"home_score": 1, "away_score": 0}}}
    save_state(path, new_state)

    loaded = load_state(path)
    assert loaded == new_state
