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
