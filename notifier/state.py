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
