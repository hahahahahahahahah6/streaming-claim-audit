from pathlib import Path


def whole_input(path):
    return Path(path).read_text(encoding='utf-8')
