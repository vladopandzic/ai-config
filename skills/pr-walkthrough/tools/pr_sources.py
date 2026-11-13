"""Whole files + a definitions index for a walkthrough page: expand context around a code panel, F12 to a definition.

Included in full: every text file the PR touches (generated code and binaries skipped), every file a panel shows, and
the files that declare the types those files use most (until a size budget runs out). Definitions are found with
regexes, not a compiler: types repo-wide (`git grep` at head), members/XAML keys/Razor components in included files.
A definition in a file that did not fit in the budget stays in the index as "ext", so the page can link out to it.

Every PR file also gets what review tracking needs: "sha" (its git blob at head, or at base when deleted), "lines" (how many
lines it has) and "vers" — the earlier blobs it had inside the PR, each with the head lines that changed since that version
and how many later commits touched it, so a file marked as reviewed at an older version can show what is new.

A modified file without its whole old text keeps just its deleted lines ("old"), so the page can show them in place.

Output (JSON): {"files": {path: {"head": text, "base": text, "added": [n], "removed": [n], "old": {n: text}, "status": "A|M|D|",
                                 "sha": blob, "lines": n, "vers": [{"sha": blob, "at": "YYYY-MM-DD", "later": n, "changed": [n]}]}},
                "index": {name: [[path, line, kind]]}, "ext": {name: [[path, line, kind]]}}

Usage: python -I pr_sources.py <repo> <base> <head> <code-panels.json> <out.json>
"""
import json
import re
import subprocess
import sys
from collections import Counter

repo, base, head, panels_path, out = sys.argv[1:6]

PR_TEXT_BUDGET = 3_000_000
EXTRA_TEXT_BUDGET = 900_000
EXTRA_MAX_FILES = 80
MAX_FILE_SIZE = 400_000
BINARY_EXT = re.compile(r'\.(dll|exe|pdb|pdx|odx|pb|png|jpe?g|gif|ico|bmp|webp|zip|7z|gz|nupkg|pdf|xlsx?|docx?|pptx?|bin|so|dylib|ttf|woff2?|eot|mp4|snk|pfx|p12)$', re.I)
GENERATED = re.compile(r'(\.Designer\.cs|ModelSnapshot\.cs|\.g\.cs|\.g\.i\.cs|AssemblyInfo\.cs|package-lock\.json|yarn\.lock|\.min\.(js|css))$', re.I)
CODE_EXT = re.compile(r'\.(cs|razor|cshtml|xaml|axaml)$', re.I)

MODS = r'(?:(?:public|private|protected|internal|static|async|override|virtual|abstract|sealed|new|partial|readonly|extern|unsafe|const|required|volatile|file)\s+)'
TYPE_DECL = re.compile(r'^\s*' + MODS + r'*(?:class|interface|record(?:\s+struct|\s+class)?|struct|enum)\s+([A-Za-z_]\w*)')
TYPE_REF = r'[\w.<>\[\],?]+(?:\s*<[^;=(){}]*>)?\??'
METHOD = re.compile(r'^(\s{0,8})' + MODS + r'*' + TYPE_REF + r'\s+([A-Za-z_]\w*)\s*(?:<[^>()]*>)?\s*\(')
PROPERTY = re.compile(r'^\s{0,8}' + MODS + r'+' + TYPE_REF + r'\s+([A-Za-z_]\w*)\s*(\{|=>|$)')
FIELD = re.compile(r'^\s{0,8}' + MODS + r'+' + TYPE_REF + r'\s+([A-Za-z_]\w*)\s*(=|;)')
NOT_A_TYPE = {'return', 'new', 'await', 'var', 'if', 'else', 'while', 'for', 'foreach', 'switch', 'case', 'throw', 'using', 'lock',
              'yield', 'goto', 'catch', 'when', 'nameof', 'typeof', 'sizeof', 'default', 'base', 'this', 'get', 'set', 'init', 'add', 'remove'}
XAML_KEY = re.compile(r'\bx:(?:Key|Name)="([A-Za-z_]\w*)"')


def git_bytes(*args):
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, check=True).stdout


def decode(raw):
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('cp1252', errors='replace')


def show(sha, path):
    try:
        raw = git_bytes('show', f'{sha}:{path}')
    except subprocess.CalledProcessError:
        return None
    if b'\0' in raw[:8000] or len(raw) > MAX_FILE_SIZE:
        return None
    return decode(raw).replace('﻿', '').replace('\r\n', '\n').replace('\t', '    ')


def changed_lines(path):
    diff = decode(git_bytes('diff', '-U0', '--no-color', '--no-ext-diff', '--no-renames', base, head, '--', path))
    added, removed = [], []
    for m in re.finditer(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', diff, re.M):
        old_start, old_len = int(m.group(1)), int(m.group(2) or 1)
        new_start, new_len = int(m.group(3)), int(m.group(4) or 1)
        removed.extend(range(old_start, old_start + old_len))
        added.extend(range(new_start, new_start + new_len))
    return added, removed


def wanted(path):
    return not BINARY_EXT.search(path) and not GENERATED.search(path)


panels = json.load(open(panels_path, encoding='utf-8'))
files = {}
size = 0

status = {}
for line in decode(git_bytes('diff', '--name-status', '--no-renames', base, head)).splitlines():
    if line:
        st, path = line.split('\t', 1)
        status[path] = st[0]

panel_sides = {}
for p in panels.values():
    panel_sides.setdefault(p['file'], set()).add(p.get('side', 'head'))

for path in sorted(set(status) | set(panel_sides), key=lambda x: (x not in panel_sides, x)):
    if not wanted(path) and path not in panel_sides:
        continue
    st = status.get(path, '')
    entry = {'status': st}
    if st != 'D':
        text = show(head, path)
        if text is not None:
            entry['head'] = text
    if st == 'D' or 'base' in panel_sides.get(path, ()):
        text = show(base, path)
        if text is not None:
            entry['base'] = text
    if 'head' not in entry and 'base' not in entry:
        continue
    weight = len(entry.get('head', '')) + len(entry.get('base', ''))
    if size + weight > PR_TEXT_BUDGET and path not in panel_sides:
        continue
    size += weight
    if st in ('A', 'M', 'D'):
        entry['added'], entry['removed'] = changed_lines(path)
        if entry['removed'] and 'base' not in entry:
            old = (show(base, path) or '').split('\n')
            entry['old'] = {n: old[n - 1] for n in entry['removed'] if n <= len(old)}
    files[path] = entry

# Repo-wide type declarations at head (C#) and Razor components (the file name is the component).
type_decls = {}
grep = decode(subprocess.run(['git', '-C', repo, 'grep', '-n', '-I', '-E', r'(class|interface|record|struct|enum) +[A-Za-z_]', head, '--', '*.cs'],
                             capture_output=True).stdout)
for line in grep.splitlines():
    parts = line.split(':', 3)
    if len(parts) < 4:
        continue
    _, path, n, text = parts
    m = TYPE_DECL.match(text)
    if m and not GENERATED.search(path):
        type_decls.setdefault(m.group(1), []).append([path, int(n), 'type'])
for path in decode(git_bytes('ls-tree', '-r', '--name-only', head)).splitlines():
    if path.endswith('.razor'):
        name = path.rsplit('/', 1)[-1][:-6]
        type_decls.setdefault(name, []).append([path, 1, 'component'])

# Pull in the files that declare the types the included code uses most.
used = Counter()
for entry in files.values():
    for text in (entry.get('head'), entry.get('base')):
        if text:
            used.update(re.findall(r'\b[A-Z][A-Za-z0-9_]*\b', text))
extra_size, extra_files = 0, 0
for name, count in used.most_common():
    decls = type_decls.get(name, [])
    if len(decls) > 2:
        continue
    for path, _, _ in decls:
        if path in files or extra_files >= EXTRA_MAX_FILES:
            continue
        text = show(head, path)
        if text is None or extra_size + len(text) > EXTRA_TEXT_BUDGET:
            continue
        files[path] = {'head': text, 'status': ''}
        extra_size += len(text)
        extra_files += 1


def declarations(path, text):
    found = []
    in_interface = False
    types_here = {m.group(1) for m in map(TYPE_DECL.match, text.split('\n')) if m}
    for n, line in enumerate(text.split('\n'), 1):
        if CODE_EXT.search(path) and not path.endswith(('.xaml', '.axaml')):
            m = TYPE_DECL.match(line)
            if m:
                found.append([m.group(1), n, 'type'])
                in_interface = ' interface ' in f' {line} '
                continue
            stripped = line.strip()
            if not stripped or stripped.startswith(('//', '*', '/*', '[', '#', '@', '<')):
                continue
            first = stripped.split()[0]
            if first in NOT_A_TYPE:
                continue
            m = METHOD.match(line)
            if m:
                has_modifiers = re.match(r'\s{0,8}' + MODS, line) is not None
                if (has_modifiers or in_interface) and m.group(2) not in NOT_A_TYPE:
                    found.append([m.group(2), n, 'ctor' if m.group(2) in types_here else 'method'])
                continue
            m = PROPERTY.match(line)
            if m:
                found.append([m.group(1), n, 'prop'])
                continue
            m = FIELD.match(line)
            if m:
                found.append([m.group(1), n, 'const' if ' const ' in f' {line} ' else 'field'])
        if path.endswith(('.xaml', '.axaml')):
            for m in XAML_KEY.finditer(line):
                found.append([m.group(1), n, 'key'])
    return found


index, ext = {}, {}
for path, entry in files.items():
    text = entry.get('head') or entry.get('base') or ''
    for name, n, kind in declarations(path, text):
        index.setdefault(name, []).append([path, n, kind])
for name, decls in type_decls.items():
    for path, n, kind in decls:
        if path in files:
            if kind == 'component':
                index.setdefault(name, []).append([path, 1, kind])
        elif name in used:
            ext.setdefault(name, []).append([path, n, kind])



def blobs(commit):
    found = {}
    for line in decode(git_bytes('ls-tree', '-r', commit)).splitlines():
        meta, path = line.split('\t', 1)
        found[path] = meta.split()[2]
    return found


def head_lines_changed_since(commit, path):
    diff = decode(git_bytes('diff', '-U0', '--no-color', '--no-ext-diff', '--no-renames', commit, head, '--', path))
    lines = []
    for m in re.finditer(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', diff, re.M):
        start, length = int(m.group(1)), int(m.group(2) or 1)
        lines.extend(range(start, start + length))
    return lines


head_blobs, base_blobs = blobs(head), blobs(base)
commits = decode(git_bytes('rev-list', '--reverse', f'{base}..{head}')).split()
commit_dates = dict(line.split(' ', 1) for line in decode(git_bytes('log', '--format=%H %cs', f'{base}..{head}')).splitlines() if line)
touched = {c: set(decode(git_bytes('diff-tree', '--no-commit-id', '--name-only', '-r', '--no-renames', c)).splitlines()) - {''} for c in commits}
for path, entry in files.items():
    if not entry['status']:
        continue
    entry['sha'] = head_blobs.get(path) or base_blobs.get(path, '')
    entry['lines'] = (entry.get('head') or entry.get('base') or '').count('\n') + 1
    if entry['status'] == 'D':
        continue
    vers, seen = [], {entry['sha']}
    for i, c in enumerate(commits[:-1]):
        if path not in touched[c]:
            continue
        sha = decode(subprocess.run(['git', '-C', repo, 'rev-parse', '--verify', '--quiet', f'{c}:{path}'], capture_output=True).stdout).strip()
        if not sha or sha in seen:
            continue
        seen.add(sha)
        later = sum(1 for d in commits[i + 1:] if path in touched[d])
        vers.append({'sha': sha, 'at': commit_dates.get(c, ''), 'later': later, 'changed': head_lines_changed_since(c, path)})
    if vers:
        entry['vers'] = vers

json.dump({'files': files, 'index': index, 'ext': ext}, open(out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
pr_count = sum(1 for e in files.values() if e['status'])
print(f'files={len(files)} (PR {pr_count}, extra {extra_files}) text={(size + extra_size) // 1024}KB '
      f'index={len(index)} names, ext={len(ext)} names')
