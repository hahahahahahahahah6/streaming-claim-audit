def records(path):
    with open(path, encoding='utf-8') as f:
        for line in f:
            yield line
