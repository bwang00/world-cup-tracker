# WeCom Match Notifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a background daemon on the Mac Mini that detects World Cup score changes and pushes goal notifications + match summaries to a WeCom group chat.

**Architecture:** A single Python script (`notifier.py`) runs as a launchd daemon. It polls `worldcup26.ir/get/games` at adaptive intervals, compares responses against a local JSON state file, and sends formatted messages to a WeCom webhook when goals or match completions are detected.

**Tech Stack:** Python 3.9 (system `/usr/bin/python3`), standard library only (`urllib.request`, `json`, `time`, `logging`, `os`, `tempfile`), macOS launchd for process management.

## Global Constraints

- Python 3.9.6 at `/usr/bin/python3` on target Mac Mini (sto@192.168.192.148)
- Zero external dependencies — standard library only
- All files live under `~/.wc-notifier/` on the Mac Mini
- State file updated atomically (write-to-temp + rename)
- State only persisted AFTER successful webhook delivery (HTTP 200)
- API response uses string types: `finished` is `"TRUE"`/`"FALSE"`, scores are string numbers or `"null"`
- Scorer strings use PostgreSQL array format: `{"Player 10'","Player 20'"}` or `"null"`
- `time_elapsed` values: `"finished"`, `"notstarted"`, or a minute string (e.g., `"62"`)
- `local_date` is US Eastern time in format `"MM/DD/YYYY HH:MM"`

---

## File Structure

```
~/.wc-notifier/
├── notifier.py          # Main script: polling loop, change detection, notification
├── config.json          # User configuration (webhook URL, intervals)
├── state.json           # Auto-generated match state (do not edit manually)
└── notifier.log         # Stdout/stderr from launchd

~/Library/LaunchAgents/
└── com.wc-notifier.plist   # launchd service definition

~/projects/world-cup-tracker/tests/
└── test_notifier.py     # Unit tests (run locally before deploying)
```

---

### Task 1: Configuration Loader & State Persistence

**Files:**
- Create: `~/.wc-notifier/config.json` (template)
- Create: `~/projects/world-cup-tracker/notifier/config.py` (config loader module, developed locally)
- Create: `~/projects/world-cup-tracker/notifier/state.py` (state read/write module)
- Test: `~/projects/world-cup-tracker/tests/test_config.py`
- Test: `~/projects/world-cup-tracker/tests/test_state.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `load_config(path: str) -> dict` — returns parsed config dict, raises `FileNotFoundError` if missing
  - `load_state(path: str) -> dict` — returns state dict, returns empty `{"matches": {}}` if file missing/corrupt
  - `save_state(path: str, state: dict) -> None` — atomic write (tempfile + os.rename)

- [ ] **Step 1: Write failing test for config loader**

```python
# ~/projects/world-cup-tracker/tests/test_config.py
import json
import os
import tempfile
import pytest
from notifier.config import load_config


def test_load_config_valid():
    cfg = {
        "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test123",
        "poll_interval_active": 30,
        "poll_interval_idle": 300,
        "poll_interval_default": 60,
        "timezone": "Asia/Shanghai",
        "tournament_end": "2026-07-20",
        "log_level": "INFO",
        "api_base_url": "https://worldcup26.ir/get"
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(cfg, f)
        path = f.name
    try:
        result = load_config(path)
        assert result["webhook_url"] == cfg["webhook_url"]
        assert result["poll_interval_active"] == 30
        assert result["tournament_end"] == "2026-07-20"
    finally:
        os.unlink(path)


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.json")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'notifier'`

- [ ] **Step 3: Implement config loader**

```python
# ~/projects/world-cup-tracker/notifier/__init__.py
# (empty file to make it a package)
```

```python
# ~/projects/world-cup-tracker/notifier/config.py
import json


def load_config(path: str) -> dict:
    """Load and return configuration from a JSON file.

    Raises FileNotFoundError if the file does not exist.
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_config.py -v
```

Expected: 2 passed

- [ ] **Step 5: Write failing test for state persistence**

```python
# ~/projects/world-cup-tracker/tests/test_state.py
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
```

- [ ] **Step 6: Run test to verify it fails**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_state.py -v
```

Expected: `ModuleNotFoundError: No module named 'notifier.state'`

- [ ] **Step 7: Implement state persistence**

```python
# ~/projects/world-cup-tracker/notifier/state.py
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
```

- [ ] **Step 8: Run all tests to verify they pass**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_config.py tests/test_state.py -v
```

Expected: 6 passed

- [ ] **Step 9: Commit**

```bash
cd ~/projects/world-cup-tracker
git add notifier/__init__.py notifier/config.py notifier/state.py tests/test_config.py tests/test_state.py
git commit -m "feat(notifier): add config loader and atomic state persistence"
```

---

### Task 2: API Client & Data Parsing

**Files:**
- Create: `~/projects/world-cup-tracker/notifier/api.py`
- Test: `~/projects/world-cup-tracker/tests/test_api.py`

**Interfaces:**
- Consumes: `load_config()` from Task 1 (for `api_base_url`)
- Produces:
  - `fetch_games(api_base_url: str) -> list[dict]` — returns list of parsed match dicts, raises `APIError` on failure
  - `parse_scorers(scorers_str: str) -> list[str]` — parses `{"Player 10'","Player 20'"}` into `["Player 10'", "Player 20'"]`
  - `parse_match(raw: dict) -> dict` — normalizes a single raw API match into clean typed dict

- [ ] **Step 1: Write failing test for scorer parser**

```python
# ~/projects/world-cup-tracker/tests/test_api.py
from notifier.api import parse_scorers, parse_match, fetch_games


def test_parse_scorers_multiple():
    raw = '{"J. Quiñones 9\'","R. Jiménez 67\'"}'
    result = parse_scorers(raw)
    assert result == ["J. Quiñones 9'", "R. Jiménez 67'"]


def test_parse_scorers_single():
    raw = '{"C. Larin 11\'"}'
    result = parse_scorers(raw)
    assert result == ["C. Larin 11'"]


def test_parse_scorers_null():
    assert parse_scorers("null") == []
    assert parse_scorers("") == []


def test_parse_scorers_with_quotes():
    raw = '{"D. Bobadilla 7\'(OG)","F. Balogun 31\'","F. Balogun 45\'+5\'","G. Reyna 90\'+8\'"}'
    result = parse_scorers(raw)
    assert len(result) == 4
    assert result[0] == "D. Bobadilla 7'(OG)"


def test_parse_match_finished():
    raw = {
        "id": "1",
        "home_team_name_en": "Mexico",
        "away_team_name_en": "South Africa",
        "home_score": "2",
        "away_score": "0",
        "home_scorers": '{"J. Quiñones 9\'","R. Jiménez 67\'"}',
        "away_scorers": "null",
        "finished": "TRUE",
        "time_elapsed": "finished",
        "type": "group",
        "group": "A",
        "local_date": "06/11/2026 13:00",
        "match_minute": "null"
    }
    result = parse_match(raw)
    assert result["id"] == "1"
    assert result["home"] == "Mexico"
    assert result["away"] == "South Africa"
    assert result["home_score"] == 2
    assert result["away_score"] == 0
    assert result["is_finished"] is True
    assert result["is_live"] is False
    assert result["home_scorers"] == ["J. Quiñones 9'", "R. Jiménez 67'"]
    assert result["away_scorers"] == []
    assert result["stage"] == "group"


def test_parse_match_not_started():
    raw = {
        "id": "97",
        "home_team_name_en": "France",
        "away_team_name_en": "Morocco",
        "home_score": "null",
        "away_score": "null",
        "home_scorers": "null",
        "away_scorers": "null",
        "finished": "FALSE",
        "time_elapsed": "notstarted",
        "type": "qf",
        "group": "QF",
        "local_date": "07/09/2026 16:00",
        "match_minute": "null"
    }
    result = parse_match(raw)
    assert result["home_score"] == 0
    assert result["away_score"] == 0
    assert result["is_finished"] is False
    assert result["is_live"] is False


def test_parse_match_live():
    raw = {
        "id": "50",
        "home_team_name_en": "Brazil",
        "away_team_name_en": "Japan",
        "home_score": "1",
        "away_score": "0",
        "home_scorers": '{"Vinicius Jr. 23\'"}',
        "away_scorers": "null",
        "finished": "FALSE",
        "time_elapsed": "25",
        "type": "r16",
        "group": "R16",
        "local_date": "07/05/2026 20:00",
        "match_minute": "25"
    }
    result = parse_match(raw)
    assert result["home_score"] == 1
    assert result["is_finished"] is False
    assert result["is_live"] is True
    assert result["minute"] == "25"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_api.py -v
```

Expected: `ModuleNotFoundError: No module named 'notifier.api'`

- [ ] **Step 3: Implement API client and parsers**

```python
# ~/projects/world-cup-tracker/notifier/api.py
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

    # Split by '","' pattern — each entry is quoted with "
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
            # Check if next is comma or end
            in_quotes = False
        elif ch == ',' and not in_quotes:
            entries.append(''.join(current).strip().strip('"'))
            current = []
            i += 1
            continue
        else:
            current.append(ch)
        i += 1

    if current:
        entries.append(''.join(current).strip().strip('"'))

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

    # Map type to human-readable stage
    stage_map = {
        "group": "小组赛",
        "r32": "32强",
        "r16": "16强",
        "qf": "8强",
        "sf": "半决赛",
        "final": "决赛",
        "third": "三四名"
    }
    match_type = raw.get("type", "group")
    stage = stage_map.get(match_type, match_type)

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
        "stage": stage,
        "local_date": raw.get("local_date", ""),
        "type": match_type,
    }


def fetch_games(api_base_url: str) -> list:
    """Fetch all games from worldcup26.ir API.

    Returns list of parsed match dicts.
    Raises APIError on network failure or invalid response.
    """
    url = f"{api_base_url}/games"
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

    return [parse_match(g) for g in raw_games]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_api.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
cd ~/projects/world-cup-tracker
git add notifier/api.py tests/test_api.py
git commit -m "feat(notifier): add API client with scorer parser and match normalizer"
```

---

### Task 3: Change Detector

**Files:**
- Create: `~/projects/world-cup-tracker/notifier/detector.py`
- Test: `~/projects/world-cup-tracker/tests/test_detector.py`

**Interfaces:**
- Consumes:
  - `parse_match()` output format from Task 2 (match dict with `id`, `home_score`, `away_score`, `is_finished`, `is_live`, etc.)
  - `load_state()` / `save_state()` from Task 1
- Produces:
  - `detect_changes(matches: list[dict], state: dict) -> tuple[list[dict], dict]` — returns `(events, updated_state)` where events is a list of event dicts and updated_state is the new state to persist
  - Event dict format: `{"type": "goal"|"match_finished", "match_id": str, "match": dict, "detail": str}`

- [ ] **Step 1: Write failing tests for change detector**

```python
# ~/projects/world-cup-tracker/tests/test_detector.py
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
    assert "goal_home_2" in new_state["matches"]["73"]["events_notified"]


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_detector.py -v
```

Expected: `ModuleNotFoundError: No module named 'notifier.detector'`

- [ ] **Step 3: Implement change detector**

```python
# ~/projects/world-cup-tracker/notifier/detector.py
import copy
import logging

logger = logging.getLogger(__name__)


def detect_changes(matches: list, state: dict) -> tuple:
    """Compare fresh match data against stored state, return events and updated state.

    Returns:
        (events, new_state) where:
        - events: list of {"type": "goal"|"match_finished", "match_id": str, "match": dict}
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
            logger.info("New match %s detected (cold start): %s %d - %d %s",
                        match_id, match["home"], home_score, away_score, match["away"])
            new_state["matches"][match_id] = {
                "home": match["home"],
                "away": match["away"],
                "home_score": home_score,
                "away_score": away_score,
                "status": "finished" if is_finished else "in_progress",
                "events_notified": _generate_existing_event_ids(home_score, away_score, is_finished)
            }
            continue

        stored = new_state["matches"][match_id]
        old_home = stored.get("home_score", 0)
        old_away = stored.get("away_score", 0)
        notified = stored.get("events_notified", [])

        # Detect goals
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
                    })
                    notified.append(event_id)

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
                })
                notified.append(event_id)

        # Update stored state
        stored["home_score"] = home_score
        stored["away_score"] = away_score
        stored["status"] = "finished" if is_finished else "in_progress"
        stored["events_notified"] = notified

    return events, new_state


def _generate_existing_event_ids(home_score: int, away_score: int, is_finished: bool) -> list:
    """Generate event IDs for an already-in-progress match (cold start)."""
    ids = []
    for i in range(1, home_score + 1):
        ids.append(f"goal_home_{i}")
    for i in range(1, away_score + 1):
        ids.append(f"goal_away_{i}")
    if is_finished:
        ids.append("match_finished")
    return ids
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_detector.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
cd ~/projects/world-cup-tracker
git add notifier/detector.py tests/test_detector.py
git commit -m "feat(notifier): add change detector with cold-start and dedup logic"
```

---

### Task 4: Notification Formatter & Sender

**Files:**
- Create: `~/projects/world-cup-tracker/notifier/sender.py`
- Test: `~/projects/world-cup-tracker/tests/test_sender.py`

**Interfaces:**
- Consumes:
  - Event dicts from Task 3: `{"type": "goal"|"match_finished", "match_id": str, "match": dict, "side": str, "goal_number": int}`
  - `config["webhook_url"]` from Task 1
- Produces:
  - `format_goal_message(event: dict) -> str` — returns markdown string for WeCom
  - `format_match_finished_message(event: dict) -> str` — returns markdown string for WeCom
  - `send_notification(webhook_url: str, message: str) -> bool` — POST to webhook, returns True on success

- [ ] **Step 1: Write failing tests for message formatting**

```python
# ~/projects/world-cup-tracker/tests/test_sender.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_sender.py -v
```

Expected: `ModuleNotFoundError: No module named 'notifier.sender'`

- [ ] **Step 3: Implement notification formatter and sender**

```python
# ~/projects/world-cup-tracker/notifier/sender.py
import json
import logging
import urllib.request
import urllib.error

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

    msg = f"⚽ 进球！\n{home} {home_score} - {away_score} {away}{minute_str}"
    if scorer_line:
        msg += scorer_line
    msg += f"\n📺 第{match['id']}场 · {stage} · 北京时间 {beijing_time}"

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
        winner = home if home_score > away_score else away if away_score > home_score else "平局"
        if winner != "平局":
            next_stage = {
                "r32": "晋级16强", "r16": "晋级8强", "qf": "晋级半决赛",
                "sf": "晋级决赛", "final": "夺冠🏆", "third": "获得季军"
            }
            advancement = f" · {winner}{next_stage.get(match['type'], '晋级')}"

    msg += f"\n\n📊 {stage}{advancement}"

    return msg


def send_notification(webhook_url: str, message: str) -> bool:
    """Send a markdown message to WeCom group webhook.

    Returns True if delivery succeeded (HTTP 200), False otherwise.
    """
    payload = json.dumps({
        "msgtype": "markdown",
        "markdown": {"content": message}
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode('utf-8')
            logger.debug("Webhook response: %s", body)
            return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        logger.error("Failed to send notification: %s", e)
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_sender.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
cd ~/projects/world-cup-tracker
git add notifier/sender.py tests/test_sender.py
git commit -m "feat(notifier): add WeCom message formatter and webhook sender"
```

---

### Task 5: Main Polling Loop & Deployment

**Files:**
- Create: `~/projects/world-cup-tracker/notifier/main.py` (entry point with polling loop)
- Create: `~/projects/world-cup-tracker/notifier/launchd/com.wc-notifier.plist`
- Create: `~/projects/world-cup-tracker/notifier/config.template.json`
- Test: `~/projects/world-cup-tracker/tests/test_main.py`

**Interfaces:**
- Consumes:
  - `load_config(path)` from Task 1
  - `load_state(path)` / `save_state(path, state)` from Task 1
  - `fetch_games(api_base_url)` from Task 2
  - `detect_changes(matches, state)` from Task 3
  - `format_goal_message(event)` / `format_match_finished_message(event)` / `send_notification(url, msg)` from Task 4
- Produces:
  - `run_once(config: dict, state_path: str) -> bool` — single poll cycle, returns True if any events processed
  - `main()` — entry point: load config, run polling loop with adaptive interval

- [ ] **Step 1: Write failing test for run_once**

```python
# ~/projects/world-cup-tracker/tests/test_main.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError: No module named 'notifier.main'`

- [ ] **Step 3: Implement main polling loop**

```python
# ~/projects/world-cup-tracker/notifier/main.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/test_main.py -v
```

Expected: 3 passed

- [ ] **Step 5: Run full test suite**

```bash
cd ~/projects/world-cup-tracker
python3 -m pytest tests/ -v
```

Expected: all tests pass (15+ tests)

- [ ] **Step 6: Create config template**

```json
// ~/projects/world-cup-tracker/notifier/config.template.json
{
  "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE",
  "poll_interval_active": 30,
  "poll_interval_idle": 300,
  "poll_interval_default": 60,
  "timezone": "Asia/Shanghai",
  "tournament_end": "2026-07-20",
  "log_level": "INFO",
  "api_base_url": "https://worldcup26.ir/get"
}
```

- [ ] **Step 7: Create launchd plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.wc-notifier</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/sto/.wc-notifier/notifier.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/sto/.wc-notifier</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/sto/.wc-notifier/notifier.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/sto/.wc-notifier/notifier.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>/Users/sto/.wc-notifier</string>
    </dict>
</dict>
</plist>
```

Save to: `~/projects/world-cup-tracker/notifier/launchd/com.wc-notifier.plist`

- [ ] **Step 8: Commit**

```bash
cd ~/projects/world-cup-tracker
git add notifier/main.py notifier/config.template.json notifier/launchd/com.wc-notifier.plist tests/test_main.py
git commit -m "feat(notifier): add main polling loop, config template, and launchd plist"
```

---

### Task 6: Deploy to Mac Mini & Smoke Test

**Files:**
- No new files created; deploy existing code to Mac Mini

**Interfaces:**
- Consumes: all modules from Tasks 1-5
- Produces: running service on Mac Mini

- [ ] **Step 1: Create deployment bundle**

Combine all notifier modules into a single self-contained `notifier.py` for deployment (the Mac Mini doesn't need the full project structure — just one script):

```bash
cd ~/projects/world-cup-tracker
# Create a combined single-file script for deployment
python3 -c "
import os

modules = ['notifier/config.py', 'notifier/state.py', 'notifier/api.py', 'notifier/detector.py', 'notifier/sender.py', 'notifier/main.py']
output = '''#!/usr/bin/env python3
\"\"\"World Cup Match Notifier - WeCom Push Service.

Combined single-file deployment. Source: ~/projects/world-cup-tracker/notifier/
\"\"\"
'''

for mod in modules:
    with open(mod) as f:
        content = f.read()
    # Remove local imports (they're all in this file now)
    lines = content.split('\n')
    cleaned = []
    for line in lines:
        if line.startswith('from notifier.'):
            continue
        cleaned.append(line)
    output += f'\n# === {mod} ===\n'
    output += '\n'.join(cleaned)

# Fix the if __name__ block
output += '''

if __name__ == \"__main__\":
    main()
'''

with open('notifier/deploy/notifier.py', 'w') as f:
    f.write(output)
print('Created notifier/deploy/notifier.py')
"
```

- [ ] **Step 2: Copy files to Mac Mini**

```bash
# Create directory on Mac Mini
ssh MacMini "mkdir -p ~/.wc-notifier && mkdir -p ~/Library/LaunchAgents"

# Copy the combined script
scp ~/projects/world-cup-tracker/notifier/deploy/notifier.py MacMini:~/.wc-notifier/notifier.py

# Copy launchd plist
scp ~/projects/world-cup-tracker/notifier/launchd/com.wc-notifier.plist MacMini:~/Library/LaunchAgents/

# Copy config template (user will need to fill in webhook key)
scp ~/projects/world-cup-tracker/notifier/config.template.json MacMini:~/.wc-notifier/config.json
```

- [ ] **Step 3: Configure webhook URL on Mac Mini**

```bash
# User must replace YOUR_KEY_HERE with actual WeCom webhook key
ssh MacMini "cat ~/.wc-notifier/config.json"
# Then edit:
# ssh MacMini "sed -i '' 's/YOUR_KEY_HERE/actual-key-here/' ~/.wc-notifier/config.json"
```

- [ ] **Step 4: Test single execution**

```bash
ssh MacMini "cd ~/.wc-notifier && /usr/bin/python3 -c '
import json, sys
sys.path.insert(0, \".\")

# Quick sanity check: can we fetch and parse games?
from notifier import *
# Since it is a single file, just run directly:
exec(open(\"notifier.py\").read().split(\"if __name__\")[0])
games = fetch_games(\"https://worldcup26.ir/get\")
print(f\"Fetched {len(games)} matches\")
live = [g for g in games if g[\"is_live\"]]
print(f\"Live now: {len(live)}\")
finished = [g for g in games if g[\"is_finished\"]]
print(f\"Finished: {len(finished)}\")
'"
```

- [ ] **Step 5: Load launchd service**

```bash
ssh MacMini "launchctl load ~/Library/LaunchAgents/com.wc-notifier.plist"
ssh MacMini "launchctl list | grep wc-notifier"
```

Expected: Shows process with PID (running)

- [ ] **Step 6: Verify logs**

```bash
ssh MacMini "tail -20 ~/.wc-notifier/notifier.log"
```

Expected: "WC Notifier started. Polling https://worldcup26.ir/get" and subsequent poll cycles

- [ ] **Step 7: Commit deploy script**

```bash
cd ~/projects/world-cup-tracker
mkdir -p notifier/deploy
git add notifier/deploy/
git commit -m "feat(notifier): add deployment bundle and deploy to Mac Mini"
```

---
