from notifier.api import parse_scorers, parse_match, fetch_games, APIError
import json
import pytest


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


def test_fetch_games_success(monkeypatch):
    """Test fetch_games with mocked HTTP response."""
    fake_response = {
        "games": [
            {
                "id": "1",
                "home_team_name_en": "Mexico",
                "away_team_name_en": "South Africa",
                "home_score": "2",
                "away_score": "0",
                "home_scorers": '{"J. Quiñones 9\'"}',
                "away_scorers": "null",
                "finished": "TRUE",
                "time_elapsed": "finished",
                "type": "group",
                "group": "A",
                "local_date": "06/11/2026 13:00",
                "match_minute": "null"
            }
        ]
    }

    class FakeResponse:
        def read(self):
            return json.dumps(fake_response).encode('utf-8')

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        return FakeResponse()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = fetch_games("https://api.example.com")
    assert len(result) == 1
    assert result[0]["home"] == "Mexico"
    assert result[0]["home_score"] == 2
    assert result[0]["is_finished"] is True


def test_fetch_games_network_error(monkeypatch):
    """Test fetch_games raises APIError on network failure."""
    import urllib.request
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(APIError):
        fetch_games("https://api.example.com")


def test_fetch_games_invalid_json(monkeypatch):
    """Test fetch_games raises APIError on invalid JSON."""
    class FakeResponse:
        def read(self):
            return b"not json at all"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        return FakeResponse()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(APIError):
        fetch_games("https://api.example.com")
