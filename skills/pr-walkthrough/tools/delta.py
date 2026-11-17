"""What changed in a PR since its walkthrough page was made, so the page can be refreshed instead of made again.

Writes delta.json: the commits between the tour's head and the new one, every file they touch with the new-head lines
that changed and the diff hunks (the page maps your comments and AI answers to the new lines with them), and which tour
snippets and zoom steps sit on changed code. Moves code-spec.json (snippet ranges and notes), zoom.json and flow.json (step lines)
to the new head, keeping a .bak of each. "summary" stays empty: the AI writes it from the commits and the diff.

Usage: python -I delta.py <repo> <old head> <new head> <tour dir> [<out delta.json>]
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time

repo, old, new, tour = sys.argv[1:5]
tour = pathlib.Path(tour)
out = pathlib.Path(sys.argv[5]) if len(sys.argv) > 5 else tour / 'delta.json'
sys.stdout.reconfigure(encoding='utf-8')


def git(*args):
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, encoding='utf-8', errors='replace', check=True).stdout


def full(sha):
    return git('rev-parse', sha).strip()


old, new = full(old), full(new)
commits = []
for line in git('log', '--reverse', '--format=%H%x1f%h%x1f%an%x1f%ad%x1f%s', '--date=short', f'{old}..{new}').splitlines():
    sha, short, author, date, subject = line.split('\x1f')
    commits.append({'sha': sha, 'short': short, 'author': author, 'date': date, 'subject': subject})

files = {}
for line in git('diff', '--name-status', '--no-renames', old, new).splitlines():
    status, path = line.split('\t', 1)
    hunks = []
    for m in re.finditer(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', git('diff', '-U0', '--no-color', old, new, '--', path), re.M):
        hunks.append([int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 1)])
    lines = [n for _, _, ns, nl in hunks for n in range(ns, ns + nl)]
    files[path] = {'status': status[0], 'lines': lines, 'hunks': hunks}


def remap(path, line):
    """Old-head line -> (new-head line, the code at it changed)."""
    off = 0
    for os_, ol, ns, nl in files.get(path, {}).get('hunks', []):
        if ol == 0:
            if line > os_:
                off += nl
                continue
            break
        if line < os_:
            break
        if line < os_ + ol:
            return max(1, ns), True
        off += nl - ol
    return line + off, False


def backup(p):
    shutil.copyfile(p, p.with_suffix(p.suffix + '.bak'))


stale_panels, stale_steps = {}, []
spec_path = tour / 'code-spec.json'
if spec_path.exists():
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    if new.startswith(spec.get('head', '')) or not old.startswith(spec.get('head', '-')):
        print(f'code-spec.json: head je {spec.get("head")}, ne {old[:7]} — ne diram')
    else:
        backup(spec_path)
        for key, panel in spec.get('panels', {}).items():
            path, changed = panel.get('file'), set(files.get(panel.get('file'), {}).get('lines', []))
            if path not in files:
                continue
            panel['ranges'] = [[remap(path, a)[0], remap(path, b)[0]] for a, b in panel.get('ranges', [])]
            if 'notes' in panel:
                panel['notes'] = {str(remap(path, int(n))[0]): t for n, t in panel['notes'].items()}
            hit = sorted(n for a, b in panel['ranges'] for n in range(a, b + 1) if n in changed)
            if hit:
                stale_panels[key] = hit
        spec['head'] = new[:7]
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding='utf-8')

zoom_path = tour / 'zoom.json'
if zoom_path.exists():
    zoom = json.loads(zoom_path.read_text(encoding='utf-8'))
    classes, moved = zoom.get('classes', {}), False
    for si, scen in enumerate(zoom.get('scenarios', [])):
        for i, step in enumerate(scen.get('steps', [])):
            at = step.get('at')
            path = at and (at.get('file') or classes.get(at.get('cls'), {}).get('file'))
            if not path or path not in files or not at.get('line'):
                continue
            at['line'], changed = remap(path, at['line'])
            moved = True
            if changed or at['line'] in files[path]['lines']:
                stale_steps.append([si, i])
    if moved:
        backup(zoom_path)
        zoom_path.write_text(json.dumps(zoom, ensure_ascii=False, indent=1), encoding='utf-8')

stale_flow_steps = []
flow_path = tour / 'flow.json'
if flow_path.exists():
    flow, moved = json.loads(flow_path.read_text(encoding='utf-8')), False
    for scen in flow.get('scenarios', []):
        for i, step in enumerate(scen.get('steps', [])):
            at = step.get('at')
            path = at and at.get('file')
            if not path or path not in files or not at.get('line'):
                continue
            at['line'], changed = remap(path, at['line'])
            moved = True
            if changed or at['line'] in files[path]['lines']:
                stale_flow_steps.append([scen.get('id'), i])
    if moved:
        backup(flow_path)
        flow_path.write_text(json.dumps(flow, ensure_ascii=False, indent=1), encoding='utf-8')

delta = {'from': old, 'to': new, 'fromShort': old[:7], 'toShort': new[:7], 'at': time.strftime('%Y-%m-%d'), 'commits': commits,
         'files': files, 'stalePanels': stale_panels, 'staleSteps': stale_steps, 'staleFlowSteps': stale_flow_steps, 'summary': ''}
prev = json.loads(out.read_text(encoding='utf-8')) if out.exists() else {}
if prev.get('from') == old and prev.get('to') == new:
    delta['summary'] = prev.get('summary', '')
out.write_text(json.dumps(delta, ensure_ascii=False, indent=1), encoding='utf-8')
print(f'{len(commits)} commita, {len(files)} fajlova, {len(stale_panels)} zastarjelih isječaka, {len(stale_steps)} zastarjelih koraka zooma, {len(stale_flow_steps)} zastarjelih koraka toka podataka')
