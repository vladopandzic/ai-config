"""Data for the tour's "Baza" view: what the PR does to the database, column by column.

Schema comes from the EF model snapshot at base and at head (tables, columns, types, keys, FKs, indexes, CHECKs), the
migration's Up() gives the DDL lines and the order of operations. Every DbContext whose snapshot the PR changes is read on
its own, with its own migrations and its provider (PostgreSQL, SQL Server or SQLite, read from the snapshot and migrations);
with more than one, table names carry the context. Who writes and reads a column is found with regexes
over the head checkout, scoped to the entity class and to receivers whose type is the entity (declared, or a lambda over
a collection of it), so generic names like Start or Name don't pick up other types. Flags come from four fixed rules.

Sample rows: the local PostgreSQL database (connection from the repo's user-secrets, read-only transaction, psql); for a table it
doesn't have, 8 example rows from Claude Code built on the schema, the code and the design-time seed (cached in db-ai.json
next to the output, --ai-refresh to redo, --no-ai to skip). The source is always recorded; the password never leaves the process.

Output (JSON): {"pr": {...}, "provider": str, "contexts": [...], "migrations": [path], "tables": [...], "sql": [{t, key, lv, cm, line}], "checks": [...], "db": {...}}

Usage: python -I pr_db.py <repo> <base> <head> <out.json> [--no-db] [--no-ai] [--ai-refresh]
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

repo, base, head, out = sys.argv[1:5]
use_db = '--no-db' not in sys.argv
use_ai = '--no-ai' not in sys.argv
AI_CACHE = Path(out).with_name('db-ai.json')

SNAPSHOT = re.compile(r'Migrations/\w*ModelSnapshot\.cs$')
MIGRATION = re.compile(r'Migrations/\d{14}_\w+\.cs$')
CODE = re.compile(r'\.(cs|razor)$')
SKIP = re.compile(r'(\.Designer\.cs|ModelSnapshot\.cs|\.g\.cs)$|/Migrations/|/(bin|obj)/')
DB_CONTEXT_ATTRIBUTE = re.compile(r'\[DbContext\(typeof\(([\w.]+)\)\)\]')
CONTEXT_SEPARATOR = ' · '
PROVIDERS = {
    'postgres': {'label': 'PostgreSQL', 'quote': ('"', '"'), 'default_schema': 'public', 'int': 'integer', 'json': 'jsonb',
                 'float': ('double precision', 'real', 'numeric', 'decimal'), 'accepts_nan': True,
                 'local_time': ('timestamp without time zone',), 'zoned_time': ('timestamp with time zone',), 'zoned_label': 'with time zone',
                 'add_column': 'ADD COLUMN'},
    'sqlserver': {'label': 'SQL Server', 'quote': ('[', ']'), 'default_schema': 'dbo', 'int': 'int', 'json': 'nvarchar(max)',
                  'float': ('float', 'real', 'decimal', 'numeric', 'money', 'smallmoney'), 'accepts_nan': False,
                  'local_time': ('datetime2', 'datetime', 'smalldatetime'), 'zoned_time': ('datetimeoffset',), 'zoned_label': 'datetimeoffset',
                  'add_column': 'ADD'},
    'sqlite': {'label': 'SQLite', 'quote': ('"', '"'), 'default_schema': None, 'int': 'INTEGER', 'json': 'TEXT',
               'float': ('REAL',), 'accepts_nan': False, 'local_time': (), 'zoned_time': (), 'zoned_label': '',
               'add_column': 'ADD COLUMN'},
}
DEFAULT_PROVIDER = 'postgres'
INTEGER_CLR_TYPES = ('int', 'long', 'short', 'byte', 'sbyte', 'ushort', 'uint', 'ulong', 'bool', 'char')
DELETE_ACTIONS = {'Cascade': 'CASCADE', 'SetNull': 'SET NULL', 'Restrict': 'RESTRICT', 'SetDefault': 'SET DEFAULT'}
AI_VALUE_FORMATS = {
    'postgres': 'brojevi kao tekst ("2.1"); timestamp without time zone "YYYY-MM-DD HH:MM:SS"; with time zone "YYYY-MM-DD HH:MM:SS+00"; niz "{...}" ili "{}"',
    'sqlserver': 'brojevi kao tekst ("2.1"); datetime2 "YYYY-MM-DD HH:MM:SS"; datetimeoffset "YYYY-MM-DD HH:MM:SS +00:00"; bit kao "0" ili "1"',
    'sqlite': 'brojevi kao tekst ("2.1"); datum i vrijeme kao tekst "YYYY-MM-DD HH:MM:SS"; bool kao "0" ili "1"',
}
FILTER_CALLS = {'Where': 'Where', 'OrderBy': 'OrderBy', 'OrderByDescending': 'OrderBy', 'ThenBy': 'OrderBy',
                'ThenByDescending': 'OrderBy', 'Join': 'Join', 'GroupJoin': 'Join', 'GroupBy': 'GroupBy'}
MEMBER = re.compile(r'^\s*(?:\[[^\]]*\]\s*)*(?:(?:public|private|protected|internal|static|async|override|virtual|abstract|sealed|new|partial|readonly)\s+)+'
                    r'[\w.<>\[\],?() ]*?\b([A-Za-z_]\w*)\s*(?:<[^>()]*>)?\s*(\(|\{|=>|$)')


def git(*args):
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout


_texts = {}


def show(sha, path):
    key = (sha, path)
    if key not in _texts:
        r = subprocess.run(['git', '-C', repo, 'show', f'{sha}:{path}'], capture_output=True)
        _texts[key] = r.stdout.decode('utf-8-sig', errors='replace').replace('\r\n', '\n') if r.returncode == 0 else None
    return _texts[key]


def layer(path):
    project = path.split('/')[0]
    if re.search(r'test', project, re.I):
        return None
    if project.endswith('.Domain') or '.Domain.' in project:
        return 'domain'
    if project.endswith('.Infrastructure') or '.Infrastructure.' in project:
        return 'ef'
    return 'web'


def block_end(text, start):
    """Index just past the brace that closes the one at text[start] (strings and chars skipped)."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if text.startswith('//', i):
            i = text.find('\n', i)
            if i < 0:
                return n
        elif text.startswith('/*', i):
            i = text.find('*/', i)
            if i < 0:
                return n
        elif c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == '\\' else 1
        elif c == "'":
            i = text.find("'", i + 2 if text[i + 1:i + 2] == '\\' else i + 1)
            if i < 0:
                return n
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def statements(body):
    """Top-level statements of a block body; nested lambda bodies stay inside their statement."""
    out, depth, cur, i = [], 0, 0, 0
    while i < len(body):
        c = body[i]
        if c == '"':
            i += 1
            while i < len(body) and body[i] != '"':
                i += 2 if body[i] == '\\' else 1
        elif c in '({':
            depth += 1
        elif c in ')}':
            depth -= 1
        elif c == ';' and depth == 0:
            out.append((cur, body[cur:i]))
            cur = i + 1
        i += 1
    return out


# ---------- EF model snapshot ----------

def detect_provider(*texts):
    """Database provider from what EF wrote into the snapshot and migrations, not from configuration."""
    text = '\n'.join(t for t in texts if t)
    if re.search(r'\bNpgsql\w*Extensions\.|"Npgsql:', text):
        return 'postgres'
    if re.search(r'\bSqlServer\w*Extensions\.|"SqlServer:', text):
        return 'sqlserver'
    if re.search(r'"Sqlite:|HasColumnType\("(TEXT|INTEGER|REAL|BLOB)"\)|type: "(TEXT|INTEGER)"', text):
        return 'sqlite'
    identifier_length = re.search(r'"Relational:MaxIdentifierLength",\s*(\d+)', text)
    if identifier_length and identifier_length.group(1) == '128':
        return 'sqlserver'
    return DEFAULT_PROVIDER


def base_type(column_type):
    return re.sub(r'\s*\([^)]*\)', '', column_type).strip()


def parse_snapshot(text, provider):
    entities = {}
    default_schema = re.search(r'\.HasDefaultSchema\("(\w+)"\)', text)

    def entity(name):
        return entities.setdefault(name, {'name': name, 'table': None, 'schema': None, 'columns': {}, 'order': [], 'key': [], 'identity': set(),
                                          'generated': set(), 'indexes': [], 'fks': [], 'checks': [], 'owned_by': None, 'owned_nav': None,
                                          'many': False, 'base': None, 'json': None})

    def walk(body, name, var):
        e = entity(name)
        for _, st in statements(body):
            s = st.strip()
            json_column = re.search(r'\.ToJson\("(\w+)"\)', s)
            if json_column and not re.match(rf'{var}\.Owns', s):
                e['json'] = json_column.group(1)
            m = re.match(rf'{var}\.(Property|PrimitiveCollection)<([^>]+(?:<[^>]*>)?[^>]*)>\("(\w+)"\)', s)
            if m:
                clr, col = m.group(2).strip(), m.group(3)
                ctype = re.search(r'HasColumnType\("([^"]+)"\)', s)
                cname = re.search(r'HasColumnName\("([^"]+)"\)', s)
                maxlen = re.search(r'HasMaxLength\((\d+)\)', s)
                value_type = clr.rstrip('?') in {'int', 'long', 'short', 'byte', 'double', 'float', 'decimal', 'bool', 'DateTime', 'DateTimeOffset',
                                                 'DateOnly', 'TimeOnly', 'TimeSpan', 'Guid'}
                nullable = clr.endswith('?') or (not value_type and '.IsRequired()' not in s)
                e['columns'][col] = {'name': cname.group(1) if cname else col, 'prop': col, 'clr': clr, 'type': ctype.group(1) if ctype else '',
                                     'nullable': nullable, 'maxLength': int(maxlen.group(1)) if maxlen else None}
                e['order'].append(col)
                if '.ValueGeneratedOnAdd()' in s:
                    e['generated'].add(col)
                continue
            m = re.match(rf'\w+PropertyBuilderExtensions\.UseIdentity\w*\({var}\.Property<[^>]+>\("(\w+)"\)\)', s)
            if m:
                e['identity'].add(m.group(1))
                continue
            m = re.match(rf'{var}\.HasBaseType\("([\w.`]+)"\)', s)
            if m:
                e['base'] = m.group(1)
                continue
            m = re.match(rf'{var}\.HasKey\(([^)]*)\)', s)
            if m:
                e['key'] = re.findall(r'"(\w+)"', m.group(1))
                continue
            m = re.match(rf'{var}\.HasIndex\(([^)]*)\)', s)
            if m:
                dbname = re.search(r'HasDatabaseName\("([^"]+)"\)', s)
                index_filter = re.search(r'HasFilter\("((?:[^"\\]|\\.)*)"\)', s)
                e['indexes'].append({'columns': re.findall(r'"(\w+)"', m.group(1)), 'unique': '.IsUnique()' in s, 'name': dbname.group(1) if dbname else None,
                                     'filter': index_filter.group(1).replace('\\"', '"') if index_filter else None})
                continue
            m = re.match(rf'{var}\.ToTable\((?:"(\w+)"(?:,\s*"(\w+)")?)?', s)
            if m:
                if m.group(1):
                    e['table'], e['schema'] = m.group(1), m.group(2)
                known = {c['name'] for c in e['checks']}
                e['checks'] += [{'name': a, 'sql': b.replace('\\"', '"')} for a, b in re.findall(r'HasCheckConstraint\("([^"]+)",\s*"((?:[^"\\]|\\.)*)"\)', s) if a not in known]
                continue
            m = re.match(rf'{var}\.HasOne\("([\w.]+)",\s*[^)]*\)', s)
            if m:
                fk = re.search(r'HasForeignKey\(([^)]*)\)', s)
                od = re.search(r'OnDelete\(DeleteBehavior\.(\w+)\)', s)
                if fk:
                    e['fks'].append({'columns': re.findall(r'"(\w+)"', fk.group(1)), 'target': m.group(1), 'onDelete': od.group(1) if od else 'ClientSetNull',
                                     'required': '.IsRequired()' in s})
                continue
            m = re.match(rf'{var}\.WithOwner\(\)', s)
            if m:
                fk = re.search(r'HasForeignKey\(([^)]*)\)', s)
                if fk:
                    e['fks'].append({'columns': re.findall(r'"(\w+)"', fk.group(1)), 'target': e['owned_by'], 'onDelete': 'Cascade', 'required': True, 'owner': True})
                continue
            m = re.match(rf'{var}\.Owns(One|Many)\("([\w.]+)",\s*"(\w+)",\s*(\w+)\s*=>', s)
            if m:
                inner_name = f'{name}.{m.group(3)}#{m.group(2)}'
                inner = entity(inner_name)
                inner['owned_by'], inner['owned_nav'], inner['many'], inner['clr'] = name, m.group(3), m.group(1) == 'Many', m.group(2)
                brace = st.index('{', m.end() - (len(st) - len(st.lstrip())))
                walk(st[brace + 1:block_end(st, brace) - 1], inner_name, m.group(4))
    for m in re.finditer(r'modelBuilder\.Entity\("([\w.`]+)",\s*(\w+)\s*=>\s*\{', text):
        brace = m.end() - 1
        walk(text[brace + 1:block_end(text, brace) - 1], m.group(1), m.group(2))

    for name, e in entities.items():
        root = e
        while root['base'] and root['base'] in entities:
            root = entities[root['base']]
        if root is not e:
            e['key'] = e['key'] or root['key']
            if not e['table'] or e['table'] == root['table']:
                e['table'], e['schema'], e['tph'] = root['table'], root['schema'], True
        if provider == 'sqlite' and len(e['key']) == 1 and e['key'][0] in e['generated'] and e['columns'].get(e['key'][0], {}).get('type') == 'INTEGER':
            e['identity'].add(e['key'][0])
    for name, e in entities.items():
        if e['owned_by']:
            owner = entities.get(e['owned_by'])
            while owner and not owner['table'] and owner['owned_by']:
                owner = entities.get(owner['owned_by'])
            owner_table = owner['table'] if owner else None
            if not e['table'] or e['table'] == owner_table:
                e['table'], e['schema'] = owner_table, owner['schema'] if owner else None
                e['split'] = True
            link = entities.get(e['owned_by'])
            while link and not link.get('tph'):
                link = entities.get(link['owned_by'])
            e['tph'] = bool(link)

    def inside_json(e):
        while e:
            if e['json']:
                return True
            e = entities.get(e['owned_by'])
        return False
    tables = {}
    for name, e in entities.items():
        if not e['table']:
            continue
        t = tables.setdefault(e['table'], {'name': e['table'], 'schema': e['schema'] or (default_schema.group(1) if default_schema else None), 'entities': [],
                                           'columns': {}, 'order': [], 'key': [], 'identity': set(), 'indexes': [], 'fks': [], 'checks': []})
        if e['json']:
            if e['json'] not in t['columns']:
                t['order'].append(e['json'])
            t['columns'][e['json']] = {'name': e['json'], 'prop': e['owned_nav'], 'clr': e.get('clr') or name, 'type': PROVIDERS[provider]['json'],
                                       'nullable': True, 'maxLength': None, 'entity': e['owned_by']}
        if inside_json(e):
            continue
        t['entities'].append(name)
        split = e.get('split')
        for prop in e['order']:
            col = dict(e['columns'][prop])
            if split:
                if prop in e['key']:
                    continue
                col['name'] = col['name'] if col['name'] != prop else f"{e['owned_nav']}_{prop}"
            if e.get('tph'):
                col['nullable'] = True
            if col['name'] not in t['columns']:
                t['order'].append(col['name'])
            col['entity'] = name
            t['columns'][col['name']] = col
        if not split:
            t['key'] = [e['columns'][k]['name'] if k in e['columns'] else k for k in e['key']]
            t['identity'] |= {e['columns'][k]['name'] for k in e['identity'] if k in e['columns']}
            t['indexes'] += e['indexes']
            t['checks'] += [c for c in e['checks'] if c not in t['checks']]
        for fk in e['fks']:
            target = entities.get(fk['target'])
            if target is None or split:
                continue
            while target.get('split') and entities.get(target['owned_by']):
                target = entities[target['owned_by']]
            t['fks'].append({**fk, 'targetTable': target['table'], 'targetColumns': target['key']})
    return tables, entities


# ---------- migration Up() ----------

def migration_ops(path):
    text = show(head, path) or ''
    up_at = text.find('void Up(')
    down_at = text.find('void Down(')
    up = text[up_at:down_at if down_at > up_at else len(text)]
    offset = text[:up_at].count('\n')
    ops = []
    for m in re.finditer(r'migrationBuilder\.(\w+)(?:<[^>]*>)?\(', up):
        start = m.end() - 1
        depth, i = 0, start
        while i < len(up):
            if up[i] == '(':
                depth += 1
            elif up[i] == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        args = up[start:i + 1]
        line = offset + up[:m.start()].count('\n') + 1
        name = re.search(r'\bname:\s*"([^"]+)"', args)
        table = re.search(r'\btable:\s*"([^"]+)"', args)
        op = {'op': m.group(1), 'line': line, 'name': name.group(1) if name else '', 'table': table.group(1) if table else ''}
        if op['op'] == 'RenameColumn':
            new_name = re.search(r'\bnewName:\s*"([^"]+)"', args)
            op['newName'] = new_name.group(1) if new_name else ''
        if op['op'] == 'CreateIndex':
            index_filter = re.search(r'\bfilter:\s*"((?:[^"\\]|\\.)*)"', args)
            op['unique'] = bool(re.search(r'\bunique:\s*true', args))
            op['filter'] = index_filter.group(1).replace('\\"', '"') if index_filter else None
        if op['op'] == 'CreateTable':
            op['table'] = op['name']
            op['cols'] = {c: offset + up[:start].count('\n') + args[:k].count('\n') + 1
                          for c, k in ((cm.group(1), cm.start()) for cm in re.finditer(r'\n\s*(\w+)\s*=\s*table\.Column<', args))}
        if op['op'] in ('DropTable', 'RenameTable'):
            op['table'] = op['name']
        ops.append(op)
    return ops


# ---------- code: who writes, reads, guards, filters ----------

def head_files():
    return [p for p in git('ls-tree', '-r', '--name-only', head).splitlines() if CODE.search(p) and not SKIP.search(p) and layer(p)]


ALL = head_files()


def grep_files(word):
    out = git('grep', '-l', '-w', word, head, '--', '*.cs', '*.razor')
    return {line.split(':', 1)[1] for line in out.splitlines() if ':' in line}


def find_class(name, sha):
    out = git('grep', '-n', '-E', rf'\b(class|record|struct)\s+{name}\b', sha, '--', '*.cs')
    for line in out.splitlines():
        _, path, n, _ = line.split(':', 3)
        if not SKIP.search(path) and layer(path):
            return path, int(n)
    return None, None


def class_range(text, decl_line):
    lines = text.split('\n')
    offset = sum(len(x) + 1 for x in lines[:decl_line - 1])
    brace = text.find('{', offset)
    semi = text.find(';', offset)
    if brace < 0 or (0 <= semi < brace and '(' in text[offset:semi]):
        return decl_line, text[:semi].count('\n') + 1
    return decl_line, text[:block_end(text, brace)].count('\n') + 1


def member_at(lines, n):
    for k in range(n - 1, max(-1, n - 400), -1):
        m = MEMBER.match(lines[k])
        if m and m.group(1) not in {'if', 'for', 'foreach', 'while', 'switch', 'return', 'new', 'using', 'catch'}:
            return m.group(1)
        if lines[k].lstrip().startswith('@code'):
            return 'kod'
    return ''


def in_initializer(lines, n):
    """Line n sits inside an object initializer (new X { A = …, }), where A is the new object's member."""
    depth = 0
    for k in range(n - 1, max(0, n - 12), -1):
        prev = lines[k - 1]
        if ';' in prev:
            return False
        depth += prev.count('}') - prev.count('{')
        if depth < 0:
            return bool(re.search(r'\bnew\b[^;]*\{?\s*$', prev) or re.search(r'\bnew\b', lines[k - 2] if k > 1 else ''))
    return False


def short(code, limit=90):
    code = re.sub(r'\s+', ' ', code.strip())
    return code if len(code) <= limit else code[:limit - 1] + '…'


def ref(path, n, desc, lyr=None):
    return {'file': path, 'line': n, 'desc': desc, 'layer': lyr or layer(path)}


def record_params(text, name):
    m = re.search(rf'record\s+(?:class\s+|struct\s+)?{name}\s*\(', text)
    if not m:
        return None
    args = split_args(text, m.end() - 1)
    return [re.findall(r'(\w+)\s*(?:=[^,]*)?$', a.strip())[0] if re.findall(r'(\w+)\s*(?:=[^,]*)?$', a.strip()) else '' for a, _ in args]


def split_args(text, open_at):
    """[(arg text, offset)] of the call whose '(' is at open_at."""
    depth, i, start, out = 0, open_at, open_at + 1, []
    while i < len(text):
        c = text[i]
        if c == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                i += 2 if text[i] == '\\' else 1
        elif c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
            if depth == 0:
                out.append((text[start:i], start))
                return out
        elif c == ',' and depth == 1:
            out.append((text[start:i], start))
            start = i + 1
        i += 1
    return out


def column_code(entity_cls, entity_file, props, dbset):
    """{prop: {writes, reads, filters, guards_domain, carriers}} for the entity's mapped properties."""
    text = show(head, entity_file) or ''
    lines = text.split('\n')
    decl = next((i + 1 for i, l in enumerate(lines) if re.search(rf'\b(class|record)\s+{entity_cls}\b', l)), 1)
    lo, hi = class_range(text, decl)
    params = {}
    for m in re.finditer(r'[(,]\s*([A-Z]\w*)\??\s+(\w+)\s*(?=[,)=])', text):
        params.setdefault(m.group(2), m.group(1))
    result = {p: {'writes': [], 'reads': [], 'filters': [], 'guards': [], 'carriers': []} for p in props}
    for p in props:
        field = '_' + p[0].lower() + p[1:]
        for n in range(lo, hi + 1):
            code = lines[n - 1]
            s = code.strip()
            if s.startswith(('//', '*', '/*')):
                continue
            if re.search(rf'\b(public|private|protected|internal)\b[^=(]*\b{p}\s*(\{{|=>)', code) or re.search(rf'\b(public|private|protected|internal)\b[^=(]*\b{field}\b\s*[=;]', code):
                continue
            if in_initializer(lines, n):
                continue
            write = re.search(rf'(?:^|[^.\w]|this\.){p}\s*=(?![=>])', code) or re.search(rf'\b{field}\s*(=(?![=>])|\.(Add|AddRange|Clear|Remove|RemoveAll|Insert)\()', code)
            if write:
                result[p]['writes'].append(ref(entity_file, n, f'{member_at(lines, n)}: {short(s)}'))
                for ident, q in re.findall(r'\b([a-z]\w*)\.([A-Z]\w*)\b', code[write.end():]):
                    if ident in params:
                        result[p]['carriers'].append({'type': params[ident], 'param': q, 'var': ident})
                        break
                continue
            if re.search(rf'(?:^|[^.\w"]|this\.){p}\b(?!\s*:)(?!\.[A-Z])', code):
                result[p]['reads'].append(ref(entity_file, n, f'{member_at(lines, n)}: {short(s)}'))
        carrier_vars = {c['var'] for c in result[p]['carriers']}
        for n in range(lo, hi + 1):
            code = lines[n - 1]
            if not re.match(r'\s*if\s*\(', code):
                continue
            mentions = re.search(rf'(?:^|[^.\w]){p}\b', code) or any(re.search(rf'\b{v}\.{c["param"]}\b', code) for c in result[p]['carriers'] for v in [c['var']])
            follow = '\n'.join(lines[n - 1:n + 2])
            if mentions and re.search(r'Result\.Failure|\bthrow\b', follow):
                result[p]['guards'].append({'layer': 'domain', 'ok': True, 'text': short(re.sub(r'^\s*if\s*', '', code), 70), 'file': entity_file, 'line': n})
        if not carrier_vars and not result[p]['writes']:
            result[p]['noDomainWrite'] = True

    collections = set()
    if dbset:
        collections.add(dbset)
    mention = sorted(grep_files(entity_cls) & set(ALL))
    holders = set()
    for path in mention:
        t = show(head, path) or ''
        found = set(re.findall(rf'<\s*{entity_cls}\s*>\??\s+([A-Z]\w*)\b(?!\s*\()', t)) | set(re.findall(rf'\b{entity_cls}\[\]\??\s+([A-Z]\w*)\b(?!\s*\()', t))
        if found:
            collections |= found
            holders |= set(re.findall(r'\b(?:class|record|struct)\s+([A-Z]\w*)', t))
    for h in sorted(holders - {entity_cls}):
        mention = sorted(set(mention) | (grep_files(h) & set(ALL)))
    coll_re = re.compile(r'\b(' + '|'.join(map(re.escape, sorted(collections))) + r')\b(?!\s*\()') if collections else None
    for p in props:
        for path in sorted(grep_files(p) & set(mention)):
            if path == entity_file or '/DesignTime/' in path or re.search(r'IEntityTypeConfiguration<', show(head, path) or ''):
                continue
            t = show(head, path) or ''
            tl = t.split('\n')
            typed = set(re.findall(rf'\b{entity_cls}\??\s+(\w+)\s*[,)=;]', t))
            for n, code in enumerate(tl, 1):
                if code.strip().startswith(('//', '*')):
                    continue
                for m in re.finditer(rf'\b(\w+)\.{p}\b', code):
                    ident = m.group(1)
                    after = code[m.end():]
                    if ident == 'Entity' and re.match(r'\s*=(?![=>])', after) and layer(path) == 'ef':
                        result[p]['writes'].append(ref(path, n, f'{member_at(tl, n)}: {short(code)}'))
                        continue
                    if re.match(r'\s*=(?![=>])', after):
                        continue
                    lam_re = re.compile(rf'\.(\w+)\(\s*\(?{ident}\)?\s*=>')
                    lam, lam_at = lam_re.search(code[:m.start()]), n
                    if not lam:
                        for k in range(n - 1, max(0, n - 40), -1):
                            lam = lam_re.search(tl[k - 1])
                            if lam:
                                lam_at = k
                                break
                    resolved = ident in typed
                    call = None
                    if not resolved and lam and coll_re:
                        chain = ' '.join(tl[max(0, lam_at - 5):lam_at - 1]) + ' ' + tl[lam_at - 1][:lam.end()]
                        chain = chain[chain.rfind(';') + 1:]
                        chain = chain[chain.rfind('=>', 0, max(0, len(chain) - 3)) + 2:] if chain.count('=>') > 1 else chain
                        if coll_re.search(chain):
                            resolved, call = True, lam.group(1) if lam_at == n else None
                    if not resolved:
                        fe = re.search(rf'foreach\s*\(\s*(?:var|{entity_cls})\s+{ident}\s+in\s+([^)]*)\)', t)
                        resolved = bool(fe and coll_re and coll_re.search(fe.group(1)))
                    if not resolved:
                        continue
                    item = ref(path, n, f'{member_at(tl, n)}: {short(code)}')
                    if call in FILTER_CALLS:
                        result[p]['filters'].append({**item, 'kind': FILTER_CALLS[call]})
                    else:
                        result[p]['reads'].append(item)
    return result


def carrier_writes(carrier, param, entity_file):
    """Where values of carrier.param are made: constructor/initializer arguments of the carrier type, outside the entity."""
    decl_path, _ = find_class(carrier, head)
    names = record_params(show(head, decl_path) or '', carrier) if decl_path else None
    found = []
    for path in sorted(grep_files(carrier) & set(ALL)):
        if path in (entity_file, decl_path) or '/DesignTime/' in path:
            continue
        t = show(head, path) or ''
        tl = t.split('\n')
        starts = [m.end() - 1 for m in re.finditer(rf'new\s+{carrier}\s*\(', t)]
        for m in re.finditer(rf'\b{carrier}\s+\w+\s*\([^;{{]*?\)\s*=>\s*new\s*\(', t):
            starts.append(m.end() - 1)
        for m in re.finditer(rf'\b{carrier}\s+\w+\s*\([^;{{]*?\)\s*\{{[^}}]*?return\s+new\s*\(', t, re.S):
            starts.append(m.end() - 1)
        for at in starts:
            args = split_args(t, at)
            for k, (a, off) in enumerate(args):
                named = re.match(r'\s*(\w+)\s*:\s*(?!:)', a)
                name = named.group(1) if named else (names[k] if names and k < len(names) else None)
                if name != param:
                    continue
                expr = a[named.end():] if named else a
                n = t[:off + len(a) - len(a.lstrip())].count('\n') + 1
                found.append({**ref(path, n, f'{member_at(tl, n)}: {short(expr)}'), 'expr': expr.strip(),
                              'via': re.findall(r'\b([a-z]\w*)\.([A-Z]\w*)\b', expr), 'text': t})
    return found


def web_guards(found):
    out = []
    for w in found:
        if '??' in w['expr']:
            out.append({'layer': 'web', 'ok': False, 'text': f"prazno → {short(w['expr'].split('??', 1)[1], 30)}", 'file': w['file'], 'line': w['line']})
        t = w['text']
        for ident, member in w['via']:
            ty = re.search(rf'\b([A-Z]\w*)\??\s+{ident}\s*[,)]', t)
            if not ty:
                continue
            for vpath in sorted(grep_files(f'AbstractValidator') & set(ALL)):
                vt = show(head, vpath) or ''
                if not re.search(rf'AbstractValidator<\s*{ty.group(1)}\s*>', vt):
                    continue
                for vm in re.finditer(rf'RuleFor\(\s*(\w+)\s*=>\s*\1\.{member}\s*\)', vt):
                    n = vt[:vm.start()].count('\n') + 1
                    chain = re.findall(r'\.(NotNull|NotEmpty|Must|MaximumLength|MinimumLength|GreaterThan\w*|LessThan\w*|InclusiveBetween|Matches|IsInEnum)\b', vt[vm.end():vm.end() + 600].split('RuleFor(')[0])
                    out.append({'layer': 'web', 'ok': True, 'text': f"{vpath.split('/')[-1].replace('.cs', '')}: {', '.join(dict.fromkeys(chain)) or 'pravilo'}",
                                'file': vpath, 'line': n})
    return out


# ---------- local database (read-only) ----------

def db_connection():
    for proj in sorted({p.split('/')[0] for p in ALL}, key=lambda x: (not x.endswith('.Infrastructure'), x)):
        csproj = Path(repo) / proj / f'{proj}.csproj'
        if not csproj.exists():
            continue
        m = re.search(r'<UserSecretsId>([^<]+)</UserSecretsId>', csproj.read_text(encoding='utf-8', errors='replace'))
        if not m:
            continue
        secrets = Path(os.environ.get('APPDATA', '')) / 'Microsoft' / 'UserSecrets' / m.group(1) / 'secrets.json'
        if not secrets.exists():
            continue
        data = json.loads(secrets.read_text(encoding='utf-8-sig'))
        flat = {}

        def walk(o, prefix=''):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, f'{prefix}{k}:')
            else:
                flat[prefix[:-1]] = str(o)
        walk(data)
        section = {k.split(':', 1)[1].lower(): v for k, v in flat.items() if k.lower().startswith('postgresql:')}
        if section.get('server') or section.get('host'):
            return {'host': section.get('server') or section.get('host'), 'port': section.get('port', '5432'), 'db': section.get('database', ''),
                    'user': section.get('userid') or section.get('username') or section.get('user', ''), 'password': section.get('password', ''), 'from': m.group(1)}
        for k, v in flat.items():
            if k.lower().startswith('connectionstrings:') and re.search(r'(?i)\b(host|server)=', v):
                kv = dict(x.split('=', 1) for x in v.split(';') if '=' in x)
                kv = {a.strip().lower(): b for a, b in kv.items()}
                return {'host': kv.get('host') or kv.get('server'), 'port': kv.get('port', '5432'), 'db': kv.get('database', ''),
                        'user': kv.get('username') or kv.get('user id') or kv.get('userid', ''), 'password': kv.get('password', ''), 'from': m.group(1)}
    return None


def psql_path():
    found = shutil.which('psql')
    if found:
        return found
    for root in (Path(r'C:\Program Files\PostgreSQL'),):
        if root.exists():
            for d in sorted(root.iterdir(), reverse=True):
                exe = d / 'bin' / 'psql.exe'
                if exe.exists():
                    return str(exe)
    return None


class Db:
    def __init__(self, conn, exe):
        self.conn, self.exe = conn, exe

    def json(self, sql):
        env = dict(os.environ, PGPASSWORD=self.conn['password'], PGCONNECT_TIMEOUT='5', PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=8000')
        r = subprocess.run([self.exe, '-w', '-X', '-q', '-A', '-t', '-h', self.conn['host'], '-p', str(self.conn['port']), '-U', self.conn['user'], '-d', self.conn['db'],
                            '-c', f'select coalesce(json_agg(x), \'[]\'::json) from ({sql}) x'],
                           capture_output=True, text=True, encoding='utf-8', env=env, timeout=30)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else f'psql {r.returncode}')
        return json.loads(r.stdout.strip() or '[]')


def qi(n, provider=DEFAULT_PROVIDER):
    left, right = PROVIDERS[provider]['quote']
    return left + n.replace(right, right * 2) + right


def table_sql(t):
    """Quoted table name for SQL, with the schema only when it is not the provider's default."""
    provider = t.get('provider', DEFAULT_PROVIDER)
    name = qi(t.get('table') or t['name'], provider)
    return f"{qi(t['schema'], provider)}.{name}" if t.get('schema') else name


def real_table(name):
    return name.split(CONTEXT_SEPARATOR)[0]


def fmt(v):
    if v is None:
        return None
    if isinstance(v, float):
        return ('%.6g' % v) if abs(v) < 1e15 else str(v)
    if isinstance(v, list):
        return '{' + ','.join('NULL' if x is None else str(x) for x in v) + '}'
    return str(v)


def db_sample(db, t):
    source = table_sql(t)
    exists = db.json(f"select to_regclass({repr(source)}) is not null as e")[0]['e']
    if not exists:
        return None
    cols = [c['name'] for c in t['columns']]
    total = db.json(f'select count(*) as n from {source}')[0]['n']
    rows = db.json(f'select {", ".join(qi(c) for c in cols)} from {source} limit 8') if total else []
    out_rows = [[fmt(r.get(c)) for c in cols] for r in rows]
    stats = {}
    for c in t['columns']:
        name, ty = c['name'], c['type']
        parts = [f'count(*) filter (where {qi(name)} is null) as nulls']
        if ty.startswith(PROVIDERS['postgres']['float']):
            parts += [f"count(*) filter (where {qi(name)} = 'NaN') as nan", f'count(*) filter (where {qi(name)} < 0) as neg',
                      f"min({qi(name)}) filter (where {qi(name)} <> 'NaN') as mn", f"max({qi(name)}) filter (where {qi(name)} <> 'NaN') as mx"]
        elif ty.startswith(('integer', 'bigint', 'smallint', 'timestamp', 'date', 'time')) and not ty.endswith('[]'):
            parts += [f'min({qi(name)}) as mn', f'max({qi(name)}) as mx', f'count(distinct {qi(name)}) as dist']
        elif ty.startswith(('character', 'text')):
            parts += [f'count(distinct {qi(name)}) as dist', f'max(length({qi(name)})) as maxlen']
        s = db.json(f'select {", ".join(parts)} from {source}')[0] if total else {}
        top = db.json(f'select {qi(name)}::text as v, count(*) as n from {source} group by 1 order by 2 desc, 1 limit 5') if total else []
        fk = next((f for f in t['foreignKeys'] if f['column'] == name), None)
        orphans = None
        if fk and total:
            tt, tc = fk['to'].split('.')
            orphans = db.json(f'select count(*) as n from {source} a where a.{qi(name)} is not null and not exists '
                              f'(select 1 from {qi(real_table(tt))} b where b.{qi(tc)} = a.{qi(name)})')[0]['n']
        pairs = [['redova', str(total)], ['NULL', str(s.get('nulls', 0))]]
        bad = []
        if 'nan' in s:
            pairs.append(['NaN', str(s['nan'])])
            pairs.append(['negativno', str(s['neg'])])
            bad += ['NaN'] if s['nan'] else []
            bad += ['negativno'] if s['neg'] else []
        if 'mn' in s and s.get('mn') is not None:
            pairs.append(['min · max', f"{fmt(s['mn'])} · {fmt(s['mx'])}"])
        if 'dist' in s:
            pairs.append(['različitih', str(s['dist'])])
        if s.get('maxlen') is not None:
            pairs.append(['najdulji', f"{s['maxlen']} zn."])
        if orphans is not None:
            pairs.append(['bez cilja (FK)', str(orphans)])
            bad += ['bez cilja (FK)'] if orphans else []
        stats[name] = {'source': 'db', 'stats': [[k, v, k in bad] for k, v in pairs], 'top': [[x['v'] if x['v'] is not None else 'NULL', x['n']] for x in top]}
    return {'source': 'db', 'total': total, 'rows': out_rows, 'stats': stats}


def seed_sources(entity_cls, carrier):
    """Design-time repository files that build the entity (or its carrier): real example values written in code."""
    names = {entity_cls} | ({carrier['type']} if carrier else set())
    found = []
    for path in sorted(set().union(*(grep_files(n) for n in names)) & set(ALL)):
        if '/DesignTime/' in path:
            found.append((path, (show(head, path) or '')[:6000]))
    return found


def sample_stats(t, rows, source):
    stats = {}
    for i, c in enumerate(t['columns']):
        vals = [r[i] if i < len(r) else None for r in rows]
        known = [v for v in vals if v is not None and v != 'NULL']
        nums = [float(v) for v in known if re.match(r'^-?\d+(\.\d+)?$', str(v))]
        pairs = [['redova', str(len(rows))], ['NULL', str(len(vals) - len(known))]]
        bad = []
        if c['type'].startswith(PROVIDERS[t.get('provider', DEFAULT_PROVIDER)]['float']):
            nan = sum(1 for v in known if str(v) == 'NaN')
            neg = sum(1 for v in nums if v < 0)
            pairs += [['NaN', str(nan)], ['negativno', str(neg)]]
            bad += (['NaN'] if nan else []) + (['negativno'] if neg else [])
        if nums:
            pairs.append(['min · max', f'{fmt(min(nums))} · {fmt(max(nums))}'])
        elif known:
            pairs.append(['različitih', str(len(set(map(str, known))))])
        counts = {}
        for v in vals:
            k = 'NULL' if v is None else str(v)
            counts[k] = counts.get(k, 0) + 1
        stats[c['name']] = {'source': source, 'stats': [[k, v, k in bad] for k, v in pairs],
                            'top': sorted(([k, n] for k, n in counts.items()), key=lambda x: -x[1])[:5]}
    return stats


def ai_sample(t, entity_cls, carrier, cache):
    """8 example rows written by Claude Code from the schema, the code that writes/guards each column and the design-time
    seed; for a table the local database doesn't have. Always labelled as an example, never as data."""
    claude = shutil.which('claude')
    if not claude:
        return None
    sig = json.dumps([[c['name'], c['type'], c['nullable']] for c in t['columns']])
    key = f"{t['name']}@{head}"
    if key in cache and cache[key].get('sig') == sig:
        return cache[key]['sample']
    cols = '\n'.join(
        f"- {c['name']}: {c['type']}, {'NULL' if c['nullable'] else 'NOT NULL'}"
        + (f", max {c['maxLength']}" if c['maxLength'] else '') + (f", {c['key']}" if c['key'] != '—' else '')
        + ''.join(f", FK → {f['to']}" for f in t['foreignKeys'] if f['column'] == c['name'])
        + ''.join(f"\n    piše: {w['file'].split('/')[-1]}:{w['line']} {w['desc']}" for w in c['writes'][:3])
        + ''.join(f"\n    čuva: {'✓' if g['ok'] else '✕'} {g['text']}" for g in c['guards'] if g['layer'] != 'db')
        for c in t['columns'])
    seeds = seed_sources(entity_cls, carrier)
    monday = date.today() - timedelta(days=date.today().weekday())
    seed_text = '\n\n'.join(f'{p}:\n```cs\n{txt}\n```' for p, txt in seeds) or '(nema)'
    provider = t.get('provider', DEFAULT_PROVIDER)
    prompt = f"""Napravi 8 primjera redova tablice "{t.get('table') or t['name']}" ({PROVIDERS[provider]['label']}), kakvi realno nastanu kad korisnici koriste aplikaciju. Služe za code review i bit će jasno označeni kao primjer, ne kao stvarni podaci.

Stupci, ovim redom (uz to što kod piše i provjerava):
{cols}

Primjeri iz DesignTime repozitorija (vrijednosti iz koda; iskoristi ih, a izraze kao thisMonday.AddHours(7) izračunaj za tjedan koji počinje u ponedjeljak {monday.day}.{monday.month}.{monday.year}.):
{seed_text}

Pravila:
- Svaki red ima konkretnu vrijednost za SVAKI stupac. NOT NULL stupac nikad nije NULL (prazan niz je "{{}}"); NULL samo gdje je stupac nullable i to ima smisla. Nikad izraz iz koda.
- Formati: {AI_VALUE_FORMATS[provider]}; enum kao broj koji baza sprema (vrijednost enuma pročitaj iz koda ako treba).
- Id od 1 nadalje; FK dosljedni (više redova može dijeliti isti roditeljski redak, a strani ključ na istu tablicu pokazuje na Id iz ovih redova).
- Najviše 2 reda smiju pokazati rubni slučaj koji kod stvarno dopušta (vidi "čuva: ✕"); za njih u "notes" na hrvatskom, jednom rečenicom, napiši zašto prolazi.
Vrati SAMO JSON, bez objašnjenja: {{"rows": [[...]], "notes": {{"<indeks reda od 0>": "razlog"}}}}"""
    try:
        r = subprocess.run([claude, '-p', '--output-format', 'json', '--strict-mcp-config', '--tools', 'Read,Grep,Glob', '--effort', 'low'],
                           input=prompt, capture_output=True, text=True, encoding='utf-8', cwd=repo, timeout=300,
                           env={name: value for name, value in os.environ.items() if name != 'ANTHROPIC_API_KEY'})
        text = json.loads(r.stdout).get('result', '')
        data = json.loads(text[text.index('{'):text.rindex('}') + 1])
    except Exception as e:
        print(f'AI primjer za {t["name"]} nije uspio: {str(e)[:160]}')
        return None
    n = len(t['columns'])
    rows = [[None if v is None or v == 'NULL' else str(v) for v in (row + [None] * n)[:n]] for row in data.get('rows', []) if isinstance(row, list)]
    if not rows:
        return None
    broken = [f"{c['name']} (red {k + 1})" for k, row in enumerate(rows) for c, v in zip(t['columns'], row) if v is None and not c['nullable']]
    if broken:
        print(f"AI primjer za {t['name']} ima NULL u NOT NULL stupcu: {', '.join(broken)}")
    sample = {'source': 'ai', 'total': None, 'rows': rows, 'notes': {str(k): v for k, v in (data.get('notes') or {}).items()},
              'seeds': [p for p, _ in seeds], 'stats': sample_stats(t, rows, 'ai')}
    cache[key] = {'sig': sig, 'sample': sample}
    return sample


# ---------- assemble ----------

def context_name(text):
    m = DB_CONTEXT_ATTRIBUTE.search(text or '')
    return m.group(1).split('.')[-1] if m else None


def contexts_in(paths):
    """One entry per DbContext whose model snapshot the PR changes, with its own migrations and provider."""
    migrations = [p for p in paths if MIGRATION.search(p) and not p.endswith('.Designer.cs')]
    contexts = []
    for snapshot in (p for p in paths if SNAPSHOT.search(p)):
        name = context_name(show(head, snapshot) or show(base, snapshot)) or snapshot.split('/')[-1].replace('ModelSnapshot.cs', '')
        contexts.append({'name': name, 'snapshot': snapshot, 'migrations': []})
    for m in migrations:
        owner = context_name(show(head, m[:-len('.cs')] + '.Designer.cs'))
        folder = m.rsplit('/', 1)[0]
        ctx = next((c for c in contexts if c['name'] == owner), None) or next((c for c in contexts if c['snapshot'].rsplit('/', 1)[0] == folder), None)
        if ctx:
            ctx['migrations'].append(m)
    for ctx in contexts:
        ctx['provider'] = detect_provider(show(head, ctx['snapshot']) or show(base, ctx['snapshot']), *(show(head, m) for m in ctx['migrations']))
    return migrations, contexts


def on_delete_sql(behavior, provider):
    action = DELETE_ACTIONS.get(behavior, 'NO ACTION')
    return 'NO ACTION' if action == 'RESTRICT' and provider == 'sqlserver' else action


def main():
    changed = git('diff', '--name-status', '-M', base, head).splitlines()
    paths = [l.split('\t')[-1] for l in changed]
    migrations, contexts = contexts_in(paths)
    result = {'pr': {'head': head, 'base': base}, 'migrations': migrations, 'tables': [], 'sql': [], 'checks': [], 'db': {'source': 'none'}}
    if not contexts:
        Path(out).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        print('PR ne dira bazu (nema promjene ModelSnapshota)')
        return
    result['provider'] = contexts[0]['provider']
    result['contexts'] = [{k: c[k] for k in ('name', 'provider', 'snapshot', 'migrations')} for c in contexts]

    ai_cache = json.loads(AI_CACHE.read_text(encoding='utf-8')) if AI_CACHE.exists() and '--ai-refresh' not in sys.argv else {}
    has_postgres = any(c['provider'] == 'postgres' for c in contexts)
    conn = db_connection() if use_db and has_postgres else None
    exe = psql_path() if conn else None
    db = Db(conn, exe) if conn and exe else None
    if db:
        try:
            db.json('select 1 as ok')
            result['db'] = {'source': 'db', 'name': conn['db'], 'host': conn['host'], 'secrets': conn['from']}
        except Exception as e:
            result['db'] = {'source': 'none', 'error': str(e)[:200]}
            db = None
    elif use_db:
        result['db'] = {'source': 'none', 'error': 'redovi iz lokalne baze zasad samo za PostgreSQL' if not has_postgres else
                        'nema connection stringa u user-secrets' if not conn else 'psql nije pronađen'}

    for ctx in contexts:
        add_context(result, ctx, len(contexts) > 1, db, ai_cache)
    if ai_cache:
        AI_CACHE.write_text(json.dumps(ai_cache, ensure_ascii=False, indent=1), encoding='utf-8')
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"tablica={len(result['tables'])} ({', '.join(t['name'] + ':' + t['status'] for t in result['tables'])}) sql={len(result['sql'])} provjera={len(result['checks'])} baza={result['db'].get('source')}")


def add_context(result, ctx, qualify, db, ai_cache):
    """Tables, SQL and checks of one DbContext; with several contexts in the PR each table name carries its context."""
    provider = ctx['provider']
    spec = PROVIDERS[provider]
    tb, eb = parse_snapshot(show(base, ctx['snapshot']) or '', provider)
    th, eh = parse_snapshot(show(head, ctx['snapshot']) or '', provider)
    ops = [dict(o, migration=m) for m in ctx['migrations'] for o in migration_ops(m)]
    tables, sql, checks = [], [], []

    def label(table_name):
        return f"{table_name}{CONTEXT_SEPARATOR}{ctx['name']}" if qualify else table_name

    def q(n):
        return qi(n, provider)

    def checks_column(column, check_sql):
        return re.search(rf'"{column}"' if provider == 'postgres' else rf'(?<!\w){re.escape(column)}(?!\w)', check_sql)

    def col_sig(c):
        return (c['type'], c['nullable'], c['maxLength'])

    statuses = {}
    for name in sorted(set(tb) | set(th)):
        if name not in th:
            statuses[name] = 'dropped'
        elif name not in tb:
            statuses[name] = 'added'
        else:
            b, h = tb[name], th[name]
            same = (set(b['columns']) == set(h['columns']) and all(col_sig(b['columns'][c]) == col_sig(h['columns'][c]) for c in h['columns'])
                    and sorted(map(str, b['indexes'])) == sorted(map(str, h['indexes'])) and sorted(str((f['columns'], f['targetTable'], f['onDelete'])) for f in b['fks'])
                    == sorted(str((f['columns'], f['targetTable'], f['onDelete'])) for f in h['fks']) and b['checks'] == h['checks'])
            statuses[name] = 'unchanged' if same else 'changed'
    touched = [n for n, s in statuses.items() if s != 'unchanged']
    neighbors = []
    for n in touched:
        model = th.get(n) or tb.get(n)
        for fk in model['fks']:
            if fk['targetTable'] and fk['targetTable'] not in touched and fk['targetTable'] not in neighbors:
                neighbors.append(fk['targetTable'])
    order = sorted(touched, key=lambda n: ({'added': 0, 'changed': 1, 'dropped': 2}[statuses[n]], n)) + neighbors

    for name in order:
        st = statuses.get(name, 'unchanged')
        model = th.get(name) if st != 'dropped' else tb.get(name)
        before = tb.get(name)
        if model is None:
            print(f'pr_db: preskačem {name} (nema je u modelu)', file=sys.stderr)
            continue
        root_entity = next((e for e in model['entities'] if not (eh.get(e) or eb.get(e) or {}).get('owned_by')), model['entities'][0])
        emodel = (eh if st != 'dropped' else eb).get(root_entity) or {}
        cls_name = (emodel.get('clr') or root_entity).split('.')[-1].split('#')[-1].split('.')[-1]
        if emodel.get('owned_by'):
            cls_name = emodel['clr'].split('.')[-1]
        entity_file, _ = find_class(cls_name, head if st != 'dropped' else base)
        config = None
        if st != 'dropped':
            hits = git('grep', '-l', '-E', rf'IEntityTypeConfiguration<\s*{cls_name}\s*>', head, '--', '*.cs')
            config = next((l.split(':', 1)[1] for l in hits.splitlines()), None)
        fk_of = {}
        for fk in model['fks']:
            for c in fk['columns']:
                fk_of[c] = fk
        idx = [i for i in model['indexes']]
        table = {'name': label(name), 'table': name, 'context': ctx['name'], 'provider': provider,
                 'schema': model['schema'] if model['schema'] != spec['default_schema'] else None,
                 'status': st, 'entity': entity_file, 'config': config, 'class': cls_name,
                 'indexes': [', '.join(i['columns']) for i in idx], 'uniqueIndexes': [', '.join(i['columns']) for i in idx if i['unique']], 'indexNames': {', '.join(i['columns']): i['name'] or f"IX_{name}_{'_'.join(i['columns'])}" for i in idx},
                 'foreignKeys': [], 'flags': [], 'columns': [], 'checksSql': [c['sql'] for c in model['checks']]}
        for fk in model['fks']:
            note = 'self-referencija: brisanje roditeljskog reda briše i redove koji na njega pokazuju' if fk['targetTable'] == name and fk['onDelete'] == 'Cascade' else \
                   'owned tip: redovi pripadaju vlasniku' if fk.get('owner') else ''
            for c, tc in zip(fk['columns'], fk['targetColumns'] or ['Id']):
                table['foreignKeys'].append({'column': c, 'to': f"{label(fk['targetTable'])}.{tc}", 'onDelete': fk['onDelete'], 'note': note})
        if emodel.get('owned_by'):
            owner = (eb if st == 'dropped' else eh).get(emodel['owned_by'], {})
            table['was'] = f"owned tip {cls_name} ({'OwnsMany' if emodel.get('many') else 'OwnsOne'} '{emodel['owned_nav']}' na {owner.get('name', emodel['owned_by']).split('.')[-1].split('#')[0]})"
        drop = next((o for o in ops if o['op'] == 'DropTable' and o['table'] == name), None)
        if st == 'dropped' and drop:
            data_moved = any(o['op'] in ('Sql', 'InsertData', 'UpdateData') and o['migration'] == drop['migration'] and o['line'] < drop['line'] for o in ops)
            if not data_moved:
                table['flags'].append({'label': 'drop bez migracije podataka', 'level': 'danger', 'file': drop['migration'], 'line': drop['line'],
                                       'why': f"Up() na liniji {drop['line']} briše tablicu, a prije toga nema Sql(...) ni InsertData koji bi prenio postojeće redove."})
            others = [label(n) for n in touched if statuses[n] == 'added' and any(o['op'] == 'CreateTable' and o['table'] == n and o['migration'] == drop['migration'] for o in ops)]
            if others:
                table['replacedBy'] = ', '.join(others)
        if st == 'unchanged':
            table['role'] = 'susjed (FK cilj)'
            incoming = [f"{label(n)}.{c}" for n in touched for fk in (th.get(n) or tb.get(n))['fks'] if fk['targetTable'] == name for c in fk['columns']]
            table['note'] = 'Na nju pokazuju: ' + ' · '.join(incoming) if incoming else ''
            table['columns'] = [{'name': k, 'type': model['columns'][k]['type'] if k in model['columns'] else spec['int'], 'nullable': False, 'key': 'PK', 'maxLength': None,
                                 'writes': [], 'reads': [], 'guards': [], 'filters': [], 'flags': []} for k in model['key']]
            tables.append(table)
            continue

        props = [model['columns'][c]['prop'] for c in model['order'] if model['columns'][c].get('entity') == root_entity]
        code = column_code(cls_name, entity_file, props, None) if st != 'dropped' and entity_file else {}
        if code:
            dbset = re.search(rf'DbSet<\s*{cls_name}\s*>\s+(\w+)', '\n'.join(show(head, p) or '' for p in sorted(grep_files('DbSet') & grep_files(cls_name))))
            if dbset:
                code = column_code(cls_name, entity_file, props, dbset.group(1))
        has_tz = [c for c in model['order'] if base_type(model['columns'][c]['type']) in spec['zoned_time']]
        renames = {o['newName']: o for o in ops if o['op'] == 'RenameColumn' and o['table'] == name}
        carriers = {}
        for cname in model['order']:
            c = model['columns'][cname]
            info = code.get(c['prop'], {}) if code else {}
            key = []
            if cname in model['key']:
                key.append('PK' + (' identity' if cname in model['identity'] else ''))
            if cname in fk_of:
                key.append('FK' + (' (self)' if fk_of[cname]['targetTable'] == name else ''))
            col = {'name': cname, 'type': c['type'] + (' (enum)' if c['clr'].rstrip('?') not in INTEGER_CLR_TYPES and c['type'] == spec['int'] else ''),
                   'nullable': c['nullable'], 'key': ' '.join(key) or '—', 'maxLength': c['maxLength'],
                   'writes': list(info.get('writes', [])), 'reads': list(info.get('reads', [])), 'filters': list(info.get('filters', [])),
                   'guards': [], 'flags': [], 'status': 'same'}
            if c['type'] == spec['int'] and c['clr'].rstrip('?') == 'int' and entity_file:
                etext = show(head, entity_file) or ''
                pt = re.search(rf'\bpublic\s+([A-Z]\w*)\??\s+{c["prop"]}\s*\{{', etext)
                if pt and pt.group(1) not in ('Int32',):
                    col['type'] = f"{spec['int']} (enum)"
            if before and st == 'changed':
                old = before['columns'].get(cname)
                col['status'] = 'added' if old is None else 'changed' if col_sig(old) != col_sig(c) else 'same'
                if old and col['status'] == 'changed':
                    col['before'] = {'type': old['type'], 'nullable': old['nullable'], 'maxLength': old['maxLength']}
                rename = renames.get(cname)
                if old is None and rename and rename['name'] in before['columns']:
                    old = before['columns'][rename['name']]
                    col['status'] = 'changed'
                    col['before'] = {'name': rename['name'], 'type': old['type'], 'nullable': old['nullable'], 'maxLength': old['maxLength']}
                    col['flags'].append({'label': 'preimenovan', 'level': 'info', 'file': rename['migration'], 'line': rename['line'],
                                         'why': f"Up() preimenuje {rename['name']} u {cname}; postojeće vrijednosti ostaju u stupcu."})
            for cr in info.get('carriers', []):
                found = carrier_writes(cr['type'], cr['param'], entity_file)
                col['writes'] += [{k: v for k, v in w.items() if k not in ('expr', 'via', 'text')} for w in found]
                col['guards'] += web_guards(found)
                carriers.setdefault(cr['type'], {'type': cr['type'], 'map': {}})['map'][cname] = cr['param']
            col['guards'] += info.get('guards', [])
            if st != 'dropped':
                if c['type'].startswith(spec['float']) and cname not in fk_of and not any(checks_column(cname, s) for s in table['checksSql']):
                    accepted = 'NaN i negativne vrijednosti' if spec['accepts_nan'] else 'negativne vrijednosti'
                    col['flags'].append({'label': 'nema CHECK', 'level': 'warn', 'why': f"{spec['label']} {c['type']} prima {accepted}, a tablica nema CHECK ograničenje za ovaj stupac."})
                if re.search(r'Id$', cname) and cname not in model['key'] and cname not in fk_of:
                    col['flags'].append({'label': 'nema FK', 'level': 'warn', 'why': 'Ime stupca kaže da pokazuje na red druge tablice, ali u modelu nema stranog ključa.'})
                if base_type(c['type']).removesuffix('[]') in spec['local_time']:
                    why = 'Vrijednost se sprema bez vremenske zone i čita kao lokalno vrijeme.'
                    if has_tz:
                        why += f" U istoj tablici {', '.join(has_tz)} je {spec['zoned_label']}."
                    col['flags'].append({'label': 'lokalno vrijeme, bez tz', 'level': 'info', 'why': why})
            db_g = []
            if not c['nullable']:
                db_g.append({'layer': 'db', 'ok': True, 'text': 'NOT NULL'})
            if c['maxLength']:
                db_g.append({'layer': 'db', 'ok': True, 'text': f"najviše {c['maxLength']} znakova"})
            if cname in fk_of:
                db_g.append({'layer': 'db', 'ok': True, 'text': f"FK → {fk_of[cname]['targetTable']}"})
            if cname in model['key']:
                db_g.append({'layer': 'db', 'ok': True, 'text': 'primarni ključ'})
            db_g += [{'layer': 'db', 'ok': True, 'text': f'CHECK {short(s, 40)}'} for s in table['checksSql'] if checks_column(cname, s)]
            db_g += [{'layer': 'db', 'ok': False, 'text': f['label'], 'why': f['why']} for f in col['flags'] if f['label'] in ('nema CHECK', 'nema FK')]
            domain_writes = [w for w in col['writes'] if w['layer'] == 'domain']
            if domain_writes and not any(g['layer'] == 'domain' for g in col['guards']) and cname not in model['key']:
                col['guards'].append({'layer': 'domain', 'ok': False, 'text': 'nema provjere u domeni', 'file': domain_writes[0]['file'], 'line': domain_writes[0]['line']})
            col['guards'] = db_g + col['guards']
            ddl_op = next((o for o in ops if o['op'] == 'CreateTable' and o['table'] == name and cname in o.get('cols', {})), None) or \
                next((o for o in ops if o['op'] in ('AddColumn', 'AlterColumn', 'RenameColumn') and o['table'] == name and o.get('newName', o['name']) == cname), None)
            if ddl_op:
                col['ddlLine'] = ddl_op['cols'][cname] if ddl_op['op'] == 'CreateTable' else ddl_op['line']
                col['ddlFile'] = ddl_op.get('migration')
            if config and st != 'dropped':
                ctext = show(head, config) or ''
                cm = re.search(rf'\.Property\(\s*\w+\s*=>\s*\w+\.{c["prop"]}\s*\)|PrimitiveCollection\(\s*\w+\s*=>\s*\w+\.{c["prop"]}\s*\)', ctext)
                if cm:
                    col['config'] = {'file': config, 'line': ctext[:cm.start()].count('\n') + 1}
            table['columns'].append(col)
        if st == 'changed':
            renamed_away = {o['name'] for o in renames.values()}
            for cname in before['order']:
                if cname not in model['columns'] and cname not in renamed_away:
                    old = before['columns'][cname]
                    table['columns'].append({'name': cname, 'type': old['type'], 'nullable': old['nullable'], 'key': '—', 'maxLength': old['maxLength'],
                                             'writes': [], 'reads': [], 'filters': [], 'guards': [], 'flags': [], 'status': 'dropped'})
        sample = None
        if db and provider == 'postgres':
            try:
                sample = db_sample(db, table)
            except Exception as e:
                result['db'].setdefault('errors', []).append(f'{label(name)}: {str(e)[:160]}')
        if sample is None and st != 'dropped' and use_ai:
            carrier = max(carriers.values(), key=lambda x: len(x['map']), default=None)
            sample = ai_sample(table, cls_name, carrier, ai_cache)
        if sample:
            sample = dict(sample)  # the AI cache keeps its own copy with stats, for the next build
            for cname, s in (sample.pop('stats', None) or {}).items():
                col = next((c for c in table['columns'] if c['name'] == cname), None)
                if col:
                    col['sample'] = s
            table['sampleRows'] = sample
        tables.append(table)

    by = {t['table']: t for t in tables}

    def table_ref(table_name):
        return table_sql(by[table_name]) if table_name in by else q(table_name)

    for o in ops:
        if o['op'] == 'DropTable':
            t = by.get(o['table'])
            sql.append({'t': f'DROP TABLE {table_ref(o["table"])};', 'key': f"{t['name']}.{t['columns'][0]['name']}" if t and t['columns'] else None,
                        'lv': 'danger' if t and t['flags'] else None, 'cm': f"-- Up():{o['line']}", 'line': o['line'], 'file': o['migration']})
        elif o['op'] == 'CreateTable' and o['table'] in by:
            t = by[o['table']]
            sql.append({'t': f'CREATE TABLE {table_sql(t)} (', 'cm': f"-- Up():{o['line']}", 'line': o['line'], 'file': o['migration']})
            for c in t['columns']:
                sqlt = c['type'].replace(' (enum)', '')
                sql.append({'t': f"  {q(c['name'])} {sqlt}{'' if c['nullable'] else ' NOT NULL'},", 'key': f"{t['name']}.{c['name']}",
                            'lv': c['flags'][0]['level'] if c['flags'] else None, 'cm': f"-- {c['key']}" if c['key'] != '—' else '-- enum' if '(enum)' in c['type'] else '',
                            'line': c.get('ddlLine'), 'file': o['migration']})
            pk = [c['name'] for c in t['columns'] if c['key'].startswith('PK')]
            if pk:
                sql.append({'t': f"  CONSTRAINT {q('PK_' + t['table'])} PRIMARY KEY ({', '.join(map(q, pk))}){',' if t['foreignKeys'] else ''}", 'key': f"{t['name']}.{pk[0]}"})
            for i, f in enumerate(t['foreignKeys']):
                tt, tc = f['to'].split('.')
                tt = real_table(tt)
                sql.append({'t': f"  CONSTRAINT {q(f'FK_{t['table']}_{tt}_{f['column']}')}\n    FOREIGN KEY ({q(f['column'])}) REFERENCES {table_ref(tt)} ({q(tc)})\n    ON DELETE {on_delete_sql(f['onDelete'], provider)}{',' if i < len(t['foreignKeys']) - 1 else ''}",
                            'key': f"{t['name']}.{f['column']}"})
            sql.append({'t': ');'})
        elif o['op'] == 'CreateIndex' and o['table'] in by:
            t = by[o['table']]
            ixcols = next((k for k, v in t['indexNames'].items() if v == o['name']), None) or o['name'].split(f"IX_{o['table']}_", 1)[-1]
            first = ixcols.split(', ')[0]
            where = f"\n  WHERE {o['filter']}" if o.get('filter') else ''
            sql.append({'t': f"CREATE {'UNIQUE ' if o.get('unique') else ''}INDEX {q(o['name'])}\n  ON {table_sql(t)} ({', '.join(map(q, ixcols.split(', ')))}){where};", 'key': f"{t['name']}.{first}",
                        'cm': f"-- Up():{o['line']}", 'line': o['line'], 'file': o['migration']})
        elif o['op'] in ('AddColumn', 'DropColumn', 'AlterColumn', 'RenameColumn') and o['table'] in by:
            t = by[o['table']]
            column = o.get('newName') or o['name']
            c = next((x for x in t['columns'] if x['name'] == column), None)
            ts = table_sql(t)
            if o['op'] == 'RenameColumn':
                text = f"EXEC sp_rename N'{ts}.{q(o['name'])}', N'{column}', N'COLUMN';" if provider == 'sqlserver' else f"ALTER TABLE {ts} RENAME COLUMN {q(o['name'])} TO {q(column)};"
            elif o['op'] == 'DropColumn' or not c:
                text = f"ALTER TABLE {ts} {'DROP COLUMN' if o['op'] == 'DropColumn' else spec['add_column'] if o['op'] == 'AddColumn' else 'ALTER COLUMN'} {q(column)};"
            else:
                nullability = ' NOT NULL' if not c['nullable'] else ' NULL' if provider == 'sqlserver' and o['op'] == 'AlterColumn' else ''
                verb = spec['add_column'] if o['op'] == 'AddColumn' else 'ALTER COLUMN'
                text = f"ALTER TABLE {ts} {verb} {q(column)} {c['type'].replace(' (enum)', '')}{nullability};"
            sql.append({'t': text, 'key': f"{t['name']}.{column}", 'cm': f"-- Up():{o['line']}", 'line': o['line'], 'file': o['migration']})
        elif o['op'] in ('Sql', 'InsertData', 'UpdateData', 'DeleteData', 'AddForeignKey', 'DropForeignKey', 'DropIndex', 'RenameTable', 'AddCheckConstraint', 'DropCheckConstraint'):
            sql.append({'t': f"-- {o['op']}({o['name'] or o['table']})", 'cm': f"-- Up():{o['line']}", 'line': o['line'], 'file': o['migration']})
        if sql and sql[-1].get('t') != '' and o['op'] in ('DropTable', 'CreateTable'):
            sql.append({'t': ''})

    for t in tables:
        ts = table_sql(t)
        if t['status'] == 'dropped' and t['flags']:
            first = t['columns'][0]['name'] if t['columns'] else ''
            checks.append({'id': f"drop:{t['name']}", 'lv': 'danger', 'when': 'prije deploya', 'title': f"Ima li redova u {t['name']} koji će nestati?",
                           'col': f"{t['name']}.{first}", 'sql': f"SELECT COUNT(*) AS redova\nFROM {ts};", 'note': t['flags'][0]['why'],
                           'local': (t.get('sampleRows') or {}).get('total') if (t.get('sampleRows') or {}).get('source') == 'db' else None})
        if t['status'] in ('added', 'changed'):
            for c in t['columns']:
                if any(f['label'] == 'nema CHECK' for f in c['flags']):
                    ident = [x['name'] for x in t['columns'] if x['key'].startswith('PK')][:1]
                    bad = f"{q(c['name'])} = 'NaN' OR {q(c['name'])} < 0" if spec['accepts_nan'] else f"{q(c['name'])} < 0"
                    checks.append({'id': f"nan:{t['name']}.{c['name']}", 'lv': 'warn', 'when': 'nakon deploya',
                                   'title': f"{c['name']}: {'NaN ili negativno' if spec['accepts_nan'] else 'negativno'}",
                                   'col': f"{t['name']}.{c['name']}", 'sql': f"SELECT {', '.join(map(q, ident + [c['name']]))}\nFROM {ts}\nWHERE {bad};",
                                   'note': next(f['why'] for f in c['flags'] if f['label'] == 'nema CHECK')})
            nofk = [c['name'] for c in t['columns'] if any(f['label'] == 'nema FK' for f in c['flags'])]
            if nofk:
                checks.append({'id': f"fk:{t['name']}", 'lv': 'warn', 'when': 'nakon deploya', 'title': f"{' / '.join(nofk)} bez FK",
                               'col': f"{t['name']}.{nofk[0]}", 'sql': f"SELECT DISTINCT {', '.join(map(q, nofk))}\nFROM {ts}\nWHERE " + '\n   OR '.join(f'{q(c)} IS NOT NULL' for c in nofk) + ';',
                               'note': 'Ime stupca kaže da pokazuje na red druge tablice, ali u modelu nema stranog ključa. Usporedi rezultat s tablicom na koju bi trebao pokazivati.',
                               'cols': [f"{t['name']}.{c}" for c in nofk]})
    if qualify and sql:
        sql.insert(0, {'t': f"-- {ctx['name']} ({spec['label']})"})
    result['tables'] += tables
    result['sql'] += sql
    result['checks'] += checks


main()
