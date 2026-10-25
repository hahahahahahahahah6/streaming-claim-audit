"""Conservative AST evidence and Markdown claim extraction."""
import ast
import os
import re
from pathlib import Path

PATTERNS = {
    'STREAMING': r'\b(?:stream\w*|incremental\w*|line[ -]by[ -]line|lazy|lazily|iterator[ -]based|yields)\b',
    'LOW_MEMORY': r'\b(?:low[ -]memory|constant[ -]memory|memory[ -]efficient|minimal memory|large[ -]files?)\b',
}
RULES = {family: 'documented-' + family.lower().replace('_', '-') + '-claim-false'
         for family in PATTERNS}


def claims(text, filename='README.md'):
    """Return one location per family; ignore fenced examples and negations."""
    result = {}
    fence = None
    prose = []
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            prose.append('')
        else:
            prose.append(line if fence is None else '')
    joined = '\n'.join(prose)
    for match in re.finditer(r'[^.!?]+(?:[.!?]|$)', joined):
        sentence = match.group()
        normalized = re.sub(r'[`*_]', '', sentence.lower()).replace('-', ' ')
        for family, pattern in PATTERNS.items():
            hit = re.search(pattern, sentence, re.I)
            if not hit:
                continue
            # Negation attached to a family phrase suppresses that family only.
            family_pattern = pattern.replace('[ -]', ' ')
            negated = re.search(
                r'\b(?:not|never|no|without|does not|do not|is not)\s+'
                r'(?:(?:support|use|provide|offer|guarantee|a|any)\s+){0,3}'
                + family_pattern, normalized, re.I)
            if not negated:
                line = joined.count('\n', 0, match.start() + hit.start()) + 1
                result.setdefault(family, {'family': family, 'file': filename, 'line': line})
    return result


def name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return name(node.value) + '.' + node.attr
    return ''


class Evidence(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.flow = {}
        self.items = []

    def kind(self, node):
        if isinstance(node, ast.Name):
            return self.flow.get(node.id)
        if isinstance(node, ast.Call):
            call = name(node.func)
            if call in ('open', 'io.open') or call.endswith('.open'):
                return 'file'
            if call in ('Path', 'pathlib.Path'):
                return 'path'
            if self.reason(node):
                return 'whole'
        return None

    def reason(self, node):
        call = name(node.func)
        attr = node.func.attr if isinstance(node.func, ast.Attribute) else ''
        receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
        if attr in ('read_text', 'read_bytes', 'readlines'):
            return attr
        if attr == 'read' and self.kind(receiver) == 'file':
            size = node.args[0] if node.args else next(
                (k.value for k in node.keywords if k.arg == 'size'), None)
            if not (isinstance(size, ast.Constant) and type(size.value) is int and size.value >= 0):
                return 'unbounded read'
        if call == 'json.load' and node.args and self.kind(node.args[0]) == 'file':
            return 'json.load(file)'
        if call == 'json.loads' and node.args and self.kind(node.args[0]) == 'whole':
            return 'json.loads(whole-file text)'
        if call == 'list' and node.args:
            arg = node.args[0]
            if self.kind(arg) == 'file' or (isinstance(arg, ast.Call) and name(arg.func) in ('csv.reader', 'csv.DictReader')):
                return 'materialized file iterator'
        if call == 'csv.reader' and node.args and isinstance(node.args[0], ast.Call) and name(node.args[0].func) == 'list':
            return 'csv.reader(list(...))'
        if call in ('pandas.read_csv', 'pandas.read_json', 'pandas.read_parquet', 'pd.read_csv', 'pd.read_json', 'pd.read_parquet') and not any(k.arg == 'chunksize' for k in node.keywords):
            return 'whole-frame load'
        return None

    def visit_Call(self, node):
        reason = self.reason(node)
        if reason:
            self.items.append({'file': self.filename, 'line': node.lineno, 'kind': reason})
        self.generic_visit(node)

    def visit_Assign(self, node):
        self.visit(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.flow[target.id] = self.kind(node.value)

    def visit_AnnAssign(self, node):
        if node.value:
            self.visit(node.value)
            if isinstance(node.target, ast.Name):
                self.flow[node.target.id] = self.kind(node.value)

    def visit_With(self, node):
        for item in node.items:
            self.visit(item.context_expr)
            if isinstance(item.optional_vars, ast.Name):
                self.flow[item.optional_vars.id] = self.kind(item.context_expr)
        for statement in node.body:
            self.visit(statement)

    def visit_FunctionDef(self, node):
        previous = self.flow
        self.flow = {}
        for statement in node.body:
            self.visit(statement)
        self.flow = previous

    visit_AsyncFunctionDef = visit_FunctionDef


def evidence(text, filename='main.py'):
    visitor = Evidence(filename)
    visitor.visit(ast.parse(text, filename=filename))
    return sorted(visitor.items, key=lambda item: (item['line'], item['kind']))


def audit(root, ignore=(), fail_on='MEDIUM'):
    root = Path(root)
    if not root.is_dir():
        raise ValueError('audit path must be an existing directory')
    found = {}
    production, test_items = [], []
    source_count = 0
    for directory, dirs, files in os.walk(root, onerror=lambda error: (_ for _ in ()).throw(error)):
        dirs[:] = sorted(d for d in dirs if d not in ('.git', '.venv', 'venv', '__pycache__', 'build', 'dist') and not d.startswith('.env') and not (Path(directory) / d).is_symlink())
        for filename in sorted(files):
            path = Path(directory) / filename
            relative = path.relative_to(root)
            parts = relative.parts
            if filename.startswith('.env') or path.is_symlink():
                continue
            if relative.as_posix() == 'README.md' or (parts[0] == 'docs' and path.suffix == '.md'):
                for family, claim in claims(path.read_text(encoding='utf-8'), relative.as_posix()).items():
                    found.setdefault(family, claim)
            if path.suffix != '.py' or any(p in ('docs', 'examples') for p in parts[:-1]):
                continue
            is_test = any(p in ('tests', 'fixtures') for p in parts[:-1]) or filename.startswith('test_') or filename.endswith('_test.py')
            items = evidence(path.read_text(encoding='utf-8'), relative.as_posix())
            if is_test:
                test_items.extend(items)
            else:
                source_count += 1
                production.extend(items)
    findings, verified = [], []
    for family, claim in sorted(found.items()):
        severity = 'HIGH' if production or not source_count else 'MEDIUM'
        items = production if production else test_items
        if not source_count or items:
            rule = RULES[family] + ('-test-only' if severity == 'MEDIUM' else '')
            if rule not in ignore:
                findings.append(dict(claim, severity=severity, rule=rule, evidence=items,
                                     message='No production Python source found.' if not source_count else 'Whole-input loading contradicts documented claim.'))
        else:
            verified.append(claim)
    failed = any(f['severity'] == 'HIGH' or fail_on == 'MEDIUM' for f in findings)
    return {'findings': findings, 'verified_claims': verified,
            'summary': {'status': 'FAIL' if failed else 'PASS', 'findings': len(findings),
                        'high': sum(f['severity'] == 'HIGH' for f in findings),
                        'medium': sum(f['severity'] == 'MEDIUM' for f in findings)}}
