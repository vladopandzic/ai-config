"""Finds, from the diff alone, what kinds of things a PR touches: the "Kod po temama" tab of a walkthrough page.

Every topic is always listed (0 = the PR doesn't touch it), so the reader also sees what a PR leaves alone. Only lines
the PR adds or removes count, never what was already in a file. Items carry file:line so a code panel can point at them;
human sentences and flags come from a separate overrides file (see build_page.py).

Rules are for .NET repos (Blazor and WPF); add rules for another stack here when its first PR comes along.

Usage: python -I pr_topics.py <repo> <base> <head> <out.json>
"""
import json
import re
import subprocess
import sys

repo, base, head, out = sys.argv[1:5]

TOPICS = [
    ('migrations', 'Baza (migracije)', 'database'),
    ('packages', 'Paketi', 'package'),
    ('settings', 'Postavke', 'settings'),
    ('jobs', 'Pozadinski poslovi', 'clock'),
    ('external', 'Vanjski servisi', 'world'),
    ('permissions', 'Prava pristupa', 'lock'),
    ('alerts', 'Alarmi i nadzor', 'bell'),
    ('ci', 'Build i CI', 'ci'),
    ('screens', 'Ekrani', 'layout'),
    ('tests', 'Testovi', 'flask'),
]
CI_FILES = r'(^|/)(Jenkinsfile[^/]*|bitbucket-pipelines\.ya?ml|azure-pipelines[^/]*\.ya?ml|\.github/workflows/[^/]+\.ya?ml|\.gitlab-ci\.ya?ml|Directory\.Build\.(props|targets)|global\.json|Dockerfile[^/]*)$'
DESTRUCTIVE_OPS = {'DropTable', 'DropColumn', 'DropForeignKey', 'DropPrimaryKey', 'RenameColumn', 'RenameTable'}


def git(*args):
    raw = subprocess.run(['git', '-C', repo, *args], capture_output=True, check=True).stdout
    lines = []
    for line in raw.split(b'\n'):
        try:
            lines.append(line.decode('utf-8'))
        except UnicodeDecodeError:
            lines.append(line.decode('cp1252', errors='replace'))
    return '\n'.join(lines)


def is_test(path):
    return bool(re.search(r'(^|[/.])Tests?([/.]|$)|\.Test\.|Tests?/', path))


def is_generated_migration(path):
    return path.endswith('.Designer.cs') or path.endswith('ModelSnapshot.cs')


def parse_diff():
    """Per file: status, added [(new_line, text)], removed [(old_line, text)]."""
    files = {}
    status = dict(reversed(l.split('\t', 1)) for l in git('diff', '--name-status', '--no-renames', base, head).splitlines() if l)
    cur = None
    old_no = new_no = 0
    for line in git('diff', '-U0', '--no-color', '--no-ext-diff', '--no-renames', base, head).splitlines():
        if line.startswith('diff --git '):
            cur = None
        elif line.startswith('+++ '):
            path = line[6:] if line[4:] != '/dev/null' else prev_path
            cur = files.setdefault(path, {'status': status.get(path, 'M'), 'added': [], 'removed': []})
        elif line.startswith('--- '):
            prev_path = line[6:]
        elif cur is not None and line.startswith('@@'):
            m = re.match(r'^@@ -(\d+)(?:,\d+)? \+(\d+)', line)
            old_no, new_no = int(m.group(1)), int(m.group(2))
        elif cur is not None and line.startswith('+'):
            cur['added'].append((new_no, line[1:].replace('﻿', '')))
            new_no += 1
        elif cur is not None and line.startswith('-'):
            cur['removed'].append((old_no, line[1:].replace('﻿', '')))
            old_no += 1
    return files


def item(topic, path, line, text, **extra):
    return {'id': f'{topic}:{path}:{line}', 'file': path, 'line': line, 'text': text.strip(), **extra}


def migration_ops(path, sha):
    source = git('show', f'{sha}:{path}')
    up = source.split('void Down(')[0]
    ops = []
    for m in re.finditer(r'migrationBuilder\.(\w+)\((?:\s*name:\s*"([^"]+)")?', up):
        line = up[:m.start()].count('\n') + 1
        ops.append({'op': m.group(1), 'name': m.group(2) or '', 'line': line,
                    'destructive': m.group(1) in DESTRUCTIVE_OPS or
                                   (m.group(1) == 'Sql' and re.search(r'\b(DELETE|DROP|TRUNCATE)\b', up[m.start():m.start() + 400], re.I) is not None)})
    return ops


files = parse_diff()
topics = {key: {'label': label, 'icon': icon, 'items': []} for key, label, icon in TOPICS}

for path, f in sorted(files.items()):
    test = is_test(path)
    added = [] if test else f['added']
    removed = [] if test else f['removed']

    if '/Migrations/' in path and path.endswith('.cs') and not is_generated_migration(path):
        sha = base if f['status'] == 'D' else head
        ops = migration_ops(path, sha)
        name = re.sub(r'^\d+_', '', path.rsplit('/', 1)[-1][:-3])
        topics['migrations']['items'].append(item('migrations', path, ops[0]['line'] if ops else 1, name,
                                                  status=f['status'], ops=ops,
                                                  destructive=any(o['destructive'] for o in ops)))

    if path.endswith('.csproj') or path.endswith('Directory.Packages.props'):
        # A removed and an added line for the same package in the same file is an upgrade (or downgrade), not two changes.
        pattern = r'Package(?:Reference|Version) Include="([^"]+)"(?: Version="([^"]+)")?'
        added_pkgs = {m.group(1): (n, m.group(2) or '') for n, t in f['added'] if (m := re.search(pattern, t))}
        removed_pkgs = {m.group(1): (n, m.group(2) or '') for n, t in f['removed'] if (m := re.search(pattern, t))}
        project = path.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        for pkg, (n, version) in added_pkgs.items():
            if pkg in removed_pkgs:
                old = removed_pkgs[pkg][1]
                major = lambda v: v.split('.')[0] if v else ''
                kind = 'upgrade' if old and version and [int(x) if x.isdigit() else x for x in re.split(r'[.-]', version)] >= [int(x) if x.isdigit() else x for x in re.split(r'[.-]', old)] else 'downgrade'
                topics['packages']['items'].append(item('packages', path, n, f'{pkg} {version}', op='~', kind=kind, package=pkg,
                                                        version=version, from_version=old, major_bump=major(old) != major(version),
                                                        project=project, test_only=is_test(path)))
            else:
                topics['packages']['items'].append(item('packages', path, n, f'{pkg} {version}', op='+', kind='new', package=pkg,
                                                        version=version, project=project, test_only=is_test(path)))
        for pkg, (n, version) in removed_pkgs.items():
            if pkg not in added_pkgs:
                topics['packages']['items'].append(item('packages', path, n, f'{pkg} {version}', op='-', kind='removed', package=pkg,
                                                        version=version, project=project, test_only=is_test(path)))

    if re.search(r'appsettings[^/]*\.json$', path):
        for n, text in added:
            if re.search(r'"\w+"\s*:', text):
                topics['settings']['items'].append(item('settings', path, n, text, op='+'))
        for n, text in removed:
            if re.search(r'"\w+"\s*:', text):
                topics['settings']['items'].append(item('settings', path, n, text, op='-'))

    for n, text in added:
        m = re.search(r'AddHostedService<(\w+)>', text) or re.search(r'class (\w+)\s*:\s*BackgroundService', text)
        if m:
            topics['jobs']['items'].append(item('jobs', path, n, m.group(1), op='+'))
        m = re.search(r'AddHttpClient<([^>]+)>', text)
        if m:
            topics['external']['items'].append(item('external', path, n, m.group(1), op='+'))
        m = re.search(r'"(https?://[^"/]+[^"]*)"', text)
        is_xml_namespace = 'xmlns' in text
        if m and not is_xml_namespace and not path.endswith('.md') and 'localhost' not in m.group(1) and 'localtest' not in m.group(1):
            topics['external']['items'].append(item('external', path, n, m.group(1), op='+'))
        m = re.search(r'RequiresPolicy\(([^)]+)\)|\[Authorize[^\]]*\]|AuthorizeView Policy="([^"]+)"', text)
        if m:
            topics['permissions']['items'].append(item('permissions', path, n, text, op='+'))
    for n, text in removed:
        m = re.search(r'AddHostedService<(\w+)>', text)
        if m:
            topics['jobs']['items'].append(item('jobs', path, n, m.group(1), op='-'))

    if re.search(r'(grafana|alert)', path, re.I) and path.endswith(('.yaml', '.yml', '.json')):
        for n, text in f['added']:
            m = re.search(r'^\s*title:\s*(.+)$', text)
            if m:
                topics['alerts']['items'].append(item('alerts', path, n, m.group(1), op='+'))

    if re.search(CI_FILES, path):
        for n, text in f['added']:
            if text.strip() and not text.strip().startswith(('//', '#')):
                topics['ci']['items'].append(item('ci', path, n, text, op='+'))
        for n, text in f['removed']:
            if text.strip() and not text.strip().startswith(('//', '#')):
                topics['ci']['items'].append(item('ci', path, n, text, op='-'))

    is_wpf_view = path.endswith('.xaml') and not path.endswith('App.xaml')
    if not test and (is_wpf_view or re.search(r'\.(razor|cshtml)$|/wwwroot/.*\.(css|js)$', path)):
        topics['screens']['items'].append(item('screens', path, 1, path.rsplit('/', 1)[-1], status=f['status']))

    if test and path.endswith('.cs'):
        topics['tests']['items'].append(item('tests', path, 1, path.rsplit('/', 1)[-1][:-3], status=f['status'],
                                             new_tests=sum(1 for _, t in f['added'] if re.search(r'\[(Test|TestCase|Fact|Theory)\b', t))))

seen_jobs = set()
topics['jobs']['items'] = [i for i in topics['jobs']['items']
                           if (i['text'], i['op']) not in seen_jobs and not seen_jobs.add((i['text'], i['op']))]

json.dump({'base': base, 'head': head, 'topics': topics}, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for key, t in topics.items():
    print(f'{key:12} {len(t["items"]):3}  ' + ' | '.join(i['text'][:40] for i in t['items'][:4]))
