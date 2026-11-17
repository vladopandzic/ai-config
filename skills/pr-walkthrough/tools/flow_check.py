"""Checks flow.json before the page is built: prints every step's code line from git so its text can be compared with
what the code really does, and fails on a missing file, a line past the end of the file or an unknown value source.

Usage: python -I flow_check.py <repo> <head> <flow.json>
"""
import json
import pathlib
import subprocess
import sys

SOURCES = {'run', 'test', 'data', 'code', 'example'}
KINDS = {'ok', 'fail', 'change'}

repo, head, flow_path = sys.argv[1:4]
sys.stdout.reconfigure(encoding='utf-8')
flow = json.loads(pathlib.Path(flow_path).read_text(encoding='utf-8'))
problems = []
file_cache = {}


def lines_of(path):
    if path not in file_cache:
        shown = subprocess.run(['git', '-C', repo, 'show', f'{head}:{path}'], capture_output=True, encoding='utf-8', errors='replace')
        file_cache[path] = shown.stdout.splitlines() if shown.returncode == 0 else None
    return file_cache[path]


for scenario in flow.get('scenarios', []):
    name = scenario.get('id') or scenario.get('name')
    if scenario.get('kind', 'ok') not in KINDS:
        problems.append(f'{name}: unknown kind {scenario.get("kind")!r}')
    print(f'\n== {name}: {scenario.get("name")}')
    for number, step in enumerate(scenario.get('steps', []), 1):
        sources = [value.get('src', 'code') for value in step.get('values', [])] + ([step['bytes'].get('src', 'code')] if step.get('bytes') else [])
        problems += [f'{name} step {number}: unknown src {src!r}' for src in sources if src not in SOURCES]
        if 'example' in sources:
            print(f'  {number}. uses an invented example value')
        at = step.get('at')
        if not at:
            print(f'  {number}. (no code line) {step.get("text", "")[:80]}')
            continue
        lines = lines_of(at['file'])
        if lines is None:
            problems.append(f'{name} step {number}: {at["file"]} is not in {head[:7]}')
            continue
        line = at.get('line', 1)
        if not 1 <= line <= len(lines):
            problems.append(f'{name} step {number}: {at["file"]} has {len(lines)} lines, step points at {line}')
            continue
        print(f'  {number}. {step.get("text", "")[:80]}')
        print(f'     {at["file"].split("/")[-1]}:{line}  {lines[line - 1].strip()[:150]}')

if problems:
    print('\nProblems:\n' + '\n'.join(problems))
    sys.exit(1)
print('\nflow.json: every line exists; now read each pair above and check the text says what the code does.')
