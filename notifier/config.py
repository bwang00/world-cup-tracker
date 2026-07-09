import json


def load_config(path: str) -> dict:
    """Load and return configuration from a JSON file.

    Raises FileNotFoundError if the file does not exist.
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
