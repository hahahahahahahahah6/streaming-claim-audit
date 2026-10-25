import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from streaming_claim_audit.audit import audit, claims, evidence, RULES

FIXTURES = Path(__file__).parent / 'fixtures'


class ClaimTests(unittest.TestCase):
    pass


CLAIMS = [
    ('streaming', 'STREAMING'), ('streams', 'STREAMING'),
    ('stream-based', 'STREAMING'), ('stream processing', 'STREAMING'),
    ('processes records as a stream', 'STREAMING'),
    ('reads data incrementally', 'STREAMING'), ('line-by-line', 'STREAMING'),
    ('line by line', 'STREAMING'), ('lazily', 'STREAMING'),
    ('lazy loading', 'STREAMING'), ('iterator-based', 'STREAMING'),
    ('yields records one at a time', 'STREAMING'),
    ('low-memory', 'LOW_MEMORY'), ('low memory', 'LOW_MEMORY'),
    ('constant-memory', 'LOW_MEMORY'), ('constant memory', 'LOW_MEMORY'),
    ('memory-efficient', 'LOW_MEMORY'), ('memory efficient', 'LOW_MEMORY'),
    ('minimal memory', 'LOW_MEMORY'), ('handles large files', 'LOW_MEMORY'),
    ('scales to large files', 'LOW_MEMORY'), ('large-file support', 'LOW_MEMORY'),
    ('STREAMING', 'STREAMING'), ('`streaming`', 'STREAMING'),
]
for index, (phrase, family) in enumerate(CLAIMS):
    def check(self, phrase=phrase, family=family):
        self.assertIn(family, claims(phrase))
    setattr(ClaimTests, 'test_claim_%02d' % index, check)

SUPPRESSED = ['not streaming', 'does not stream', 'no streaming support',
              'not low-memory', 'no constant memory', 'without lazy loading',
              '```\nstreaming\n```', '~~~md\nlow memory\n~~~',
              'An ordinary command-line utility.']
for index, phrase in enumerate(SUPPRESSED):
    def check(self, phrase=phrase):
        self.assertEqual(claims(phrase), {})
    setattr(ClaimTests, 'test_suppression_%02d' % index, check)


class EvidenceTests(unittest.TestCase):
    pass

POSITIVE = [
    'Path(p).read_text()', 'Path(p).read_bytes()',
    'f = open(p)\nf.read()', 'f = io.open(p)\nf.read()',
    'with open(p) as f:\n f.read()',
    'with Path(p).open() as f:\n f.read()',
    'f = open(p)\nf.readlines()', 'x.readlines()',
    'f = open(p)\nlist(f)', 'f = open(p)\njson.load(f)',
    'f = open(p)\ndata = f.read()\njson.loads(data)',
    'data = Path(p).read_text()\njson.loads(data)',
    'csv.reader(list(rows))', 'list(csv.reader(f))',
    'list(csv.DictReader(f))', 'pandas.read_csv(p)',
    'pandas.read_json(p)', 'pandas.read_parquet(p)', 'pd.read_csv(p)',
    'f = open(p)\nf.read().splitlines()',
    'if False:\n Path(p).read_text()',
    'f = open(p)\nf.read(-1)', 'f = open(p)\nf.read(size=n)',
    'f = open(p)\ng = f\ng.read()',
]
NEGATIVE = [
    'with open(p) as f:\n for line in f:\n  print(line)',
    'with open(p) as f:\n while True:\n  line = f.readline()\n  if not line: break',
    'f = open(p)\nf.read(4096)', 'f = open(p)\nf.read(size=4096)',
    'with open(p) as f:\n for line in f:\n  json.loads(line)',
    'for row in csv.reader(f):\n print(row)',
    'for row in csv.DictReader(f):\n print(row)',
    'f = open(p)\niter(f)', 'f = open(p)\n(x for x in f)',
    'with Path(p).open() as f:\n for line in f:\n  print(line)',
    'with Path(p).open() as f:\n f.read(4096)',
    'pandas.read_csv(p, chunksize=100)',
    'pandas.read_json(p, chunksize=100)',
    'pandas.read_parquet(p, chunksize=100)',
    'def parse(text):\n return json.loads(text)',
    'def a():\n f = open(p)\ndef b():\n f.read()',
    'f = open(p)\nf = other\nf.read()',
]
for positive, snippets in ((True, POSITIVE), (False, NEGATIVE)):
    for index, source in enumerate(snippets):
        def check(self, source=source, positive=positive):
            self.assertEqual(bool(evidence(source)), positive)
        setattr(EvidenceTests, 'test_%s_%02d' % ('read_all' if positive else 'excluded', index), check)


class AuditTests(unittest.TestCase):
    def project(self, readme='streaming, constant memory', source='for line in open(p):\n print(line)'):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / 'README.md').write_text(readme, encoding='utf-8')
        if source is not None:
            (root / 'main.py').write_text(source, encoding='utf-8')
        return root

    def test_good(self):
        result = audit(FIXTURES / 'good')
        self.assertEqual(result['summary']['status'], 'PASS')
        self.assertIn('STREAMING', [c['family'] for c in result['verified_claims']])

    def test_bad_grouping(self):
        result = audit(FIXTURES / 'bad')
        self.assertEqual(result['summary']['high'], 2)
        for finding in result['findings']:
            self.assertEqual(len(finding['evidence']), 3)
            self.assertEqual([i['line'] for i in finding['evidence']], [6, 8, 10])

    def test_testonly(self):
        result = audit(FIXTURES / 'testonly')
        self.assertEqual(result['summary']['medium'], 2)
        self.assertEqual(result['summary']['status'], 'FAIL')

    def test_threshold(self):
        result = audit(FIXTURES / 'testonly', fail_on='HIGH')
        self.assertEqual(result['summary']['status'], 'PASS')
        self.assertEqual(len(result['findings']), 2)

    def test_ignore(self):
        result = audit(FIXTURES / 'bad', ignore=RULES.values())
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['summary']['status'], 'PASS')

    def test_no_claims(self):
        self.assertEqual(audit(self.project('ordinary utility', 'Path(p).read_text()'))['summary']['status'], 'PASS')

    def test_no_source(self):
        result = audit(self.project(source=None))
        self.assertEqual(result['summary']['high'], 2)
        self.assertTrue(all(not f['evidence'] for f in result['findings']))

    def test_docs_nested(self):
        root = self.project('ordinary utility', 'Path(p).read_text()')
        (root / 'docs' / 'nested').mkdir(parents=True)
        (root / 'docs' / 'nested' / 'guide.md').write_text('streaming', encoding='utf-8')
        self.assertEqual(audit(root)['summary']['high'], 1)

    def test_other_markdown_ignored(self):
        root = self.project('ordinary utility')
        (root / 'OTHER.md').write_text('streaming', encoding='utf-8')
        self.assertEqual(audit(root)['verified_claims'], [])

    def test_symlink(self):
        root = self.project()
        (root / 'linked.py').symlink_to(FIXTURES / 'bad' / 'main.py')
        (root / 'linked').symlink_to(FIXTURES / 'bad', target_is_directory=True)
        self.assertEqual(audit(root)['summary']['status'], 'PASS')

    def test_unreadable_root(self):
        with patch('streaming_claim_audit.audit.os.walk', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                audit(self.project())

    def test_invalid_syntax(self):
        with self.assertRaises(SyntaxError):
            audit(self.project(source='def !'))

    def test_family_specific_negation(self):
        self.assertEqual(set(claims('Not streaming but constant memory.')), {'LOW_MEMORY'})

    def test_separate_sentences(self):
        self.assertIn('STREAMING', claims('Not streaming. Another API streams data.'))

    def test_fence_location(self):
        self.assertEqual(claims('```\nstreaming\n```\nStreams data.')['STREAMING']['line'], 4)

    def test_function_flow(self):
        items = evidence('def load(p):\n with open(p) as f:\n  data = f.read()\n  return json.loads(data)')
        self.assertEqual(len(items), 2)


for index, location in enumerate(('tests/helper.py', 'fixtures/helper.py', 'test_helper.py', 'helper_test.py', 'docs/helper.py', 'examples/helper.py')):
    def check(self, location=location):
        root = self.project()
        path = root / location
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('Path(p).read_text()', encoding='utf-8')
        result = audit(root)
        self.assertEqual(result['summary']['high'], 0)
        self.assertEqual(result['summary']['medium'], 0 if location.startswith(('docs/', 'examples/')) else 2)
    setattr(AuditTests, 'test_source_exclusion_%02d' % index, check)


class CLITests(unittest.TestCase):
    def run_cli(self, *args, **kwargs):
        return subprocess.run([sys.executable, '-m', 'streaming_claim_audit', *map(str, args)], capture_output=True, text=True, **kwargs)

    def test_good(self):
        run = self.run_cli(FIXTURES / 'good')
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), 'PASS')

    def test_bad_json(self):
        run = self.run_cli(FIXTURES / 'bad', '--json')
        self.assertEqual(run.returncode, 2)
        result = json.loads(run.stdout)
        self.assertEqual(set(result), {'findings', 'verified_claims', 'summary'})
        self.assertEqual(result['summary']['high'], 2)

    def test_testonly_default(self):
        run = self.run_cli(FIXTURES / 'testonly')
        self.assertEqual(run.returncode, 2)
        self.assertEqual(run.stdout.count('MEDIUM '), 2)

    def test_testonly_high(self):
        run = self.run_cli(FIXTURES / 'testonly', '--fail-on', 'HIGH')
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.count('MEDIUM '), 2)

    def test_version(self):
        run = self.run_cli('--version')
        self.assertEqual((run.returncode, run.stdout.strip()), (0, '0.1.0'))

    def test_bad_path(self):
        self.assertEqual(self.run_cli(FIXTURES / 'missing').returncode, 1)

    def test_bad_option(self):
        self.assertEqual(self.run_cli('--unknown').returncode, 1)

    def test_bad_threshold(self):
        self.assertEqual(self.run_cli('--fail-on', 'LOW').returncode, 1)

    def test_ignore_cli(self):
        run = self.run_cli(FIXTURES / 'bad', '--ignore', ','.join(RULES.values()))
        self.assertEqual((run.returncode, run.stdout.strip()), (0, 'PASS'))

    def test_verbose(self):
        self.assertIn('VERIFIED STREAMING', self.run_cli(FIXTURES / 'good', '--verbose').stdout)

    def test_json_verified(self):
        self.assertEqual(len(json.loads(self.run_cli(FIXTURES / 'good', '--json').stdout)['verified_claims']), 1)

    def test_default_path(self):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        self.assertEqual(self.run_cli(cwd=FIXTURES / 'good', env=env).returncode, 0)


if __name__ == '__main__':
    unittest.main()
