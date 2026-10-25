# streaming-claim-audit

Version 0.1.0. An offline, stdlib-only CLI that compares documented streaming
and low-memory promises with static whole-input loading patterns in Python
source. It never executes audited code, makes network requests, or opens
`.env` files. No runtime dependencies. Requires Python 3.9 or newer.

## Install and use

```sh
python3 -m pip install .
streaming-claim-audit /path/to/project
python3 -m streaming_claim_audit /path/to/project --json
streaming-claim-audit --version
streaming-claim-audit tests/fixtures/testonly --fail-on HIGH
streaming-claim-audit . --verbose --ignore documented-streaming-claim-false
```

The path defaults to `.`. Exit codes: **0 PASS**, **2 FAIL**, **1 usage/input
error**. The default `--fail-on MEDIUM` fails for HIGH or MEDIUM;
`--fail-on HIGH` still prints MEDIUM findings but allows them to pass.
`--ignore RULE,...` removes named rules entirely. `--verbose` prints verified
claims. `--json` emits an object with `findings`, `verified_claims`, and
`summary`; each finding includes its documentation location and all evidence
locations. A verified claim means no matching evidence was found, not a proof.

## Scope and rules

Claims come only from root `README.md` and `docs/**/*.md`. Fenced code is
excluded; inline code counts. Negation suppresses the corresponding family
within a sentence. Streaming stems include stream, incremental, line-by-line,
lazy/lazily, iterator-based and yields. Low-memory stems include low memory,
constant memory, memory efficient, minimal memory and large file variants.

Production source includes recursive `*.py` files except `tests/`, `fixtures/`,
`docs/`, `examples/`, `test_*.py`, and `*_test.py`. Symlinked files and
directories are skipped, as are `.git`, `.venv`, `venv`, `__pycache__`, `build`,
and `dist` directories. Files and directories beginning with `.env` are never
opened. Invalid source syntax or unreadable inputs produce an input error.

Each family produces at most one finding, carrying every relevant evidence
item. Production evidence, or claims without production source, yields HIGH:

- `documented-streaming-claim-false`
- `documented-low-memory-claim-false`

Evidence confined to test/fixture code yields MEDIUM:

- `documented-streaming-claim-false-test-only`
- `documented-low-memory-claim-false-test-only`

Evidence includes whole-file `read_text`, `read_bytes`, unbounded file `read`,
`readlines`, file/list and CSV materialization, file-derived JSON loading and
pandas whole-frame call patterns. Direct file iteration, literal-size chunked
reads, line iteration with `json.loads(line)`, directly iterated CSV readers,
and generators do not count. No documented claims means PASS, regardless of
evidence. There are no reverse rules for undocumented streaming behavior.

## Differentiation

Memory profilers and tracemalloc observe runtime allocations; this tool checks
documentation promises against source without running the target. Bandit and
Ruff flag code patterns without relating them to those promises.
format-claim-audit checks which formats are supported, readonly-claim-audit
checks writes, and schema-claim-audit checks field names. None checks how much
input is held in memory. `wc` and file-size tools measure actual input bytes
rather than comparing documentation with implementation.

## Honest limitations

This is static pattern matching, not semantic judgement or a memory profiler.
Dead and unreachable code counts. Whole-file configuration reads may be small
and harmless, and a project may expose both streaming and non-streaming APIs;
findings require human review. Variable file objects and file-derived text are
tracked only through simple same-function assignments, not across calls,
containers or complex control flow. Import aliases are not generally resolved.
Pandas call-name matching (`pandas` and `pd`) does not verify imports; a
`chunksize` keyword suppresses it regardless of its value. Chunked-read detection
recognizes only literal nonnegative integer sizes; computed sizes may be flagged.
Arbitrary third-party loaders, wrappers, and memory growth outside the listed
patterns are not detected. Negation and sentence extraction are heuristic,
not a natural-language understanding system. No evidence is not proof of
bounded memory. This auditor itself loads source and documentation into memory.

## Development and validation

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m build
```

The sdist includes tests and fixtures via `MANIFEST.in`. The good fixture
passes with a verified STREAMING claim. The bad fixture produces exactly two
HIGH findings. The testonly fixture produces two MEDIUM findings and passes
only when `--fail-on HIGH` is used (or the relevant rules are ignored).

Licensed under the MIT License; see LICENSE.
