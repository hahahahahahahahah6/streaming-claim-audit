import json
from pathlib import Path


def records(path):
    text = Path(path).read_text(encoding='utf-8')
    with open(path, encoding='utf-8') as f:
        data = f.read()
    with open(path, encoding='utf-8') as f:
        parsed = json.load(f)
    return text, data, parsed
