"""Builds the code panels (the stops of the code tour) for a walkthrough page.

Code always comes from git (never retyped), with real line numbers. Each line is marked new (added in the PR),
removed (deleted in the PR, when the panel shows the base version) or unchanged, from `git diff -U0 base head`.
Only the human sentences in `notes` are written by hand.

Spec (JSON):
{
  "repo": "<local clone>", "base": "<merge-base sha>", "head": "<head sha>",
  "panels": {
    "<key>": {
      "title": "Zašto se narudžba ne sprema", "sub": "Provjera prije spremanja",
      "file": "Shop.Api/Orders/OrderValidator.cs",
      "side": "head" | "base",            # base = show the old code (e.g. something the PR removed)
      "ranges": [[50, 53], [111, 117]],    # inclusive line ranges; a gap row is shown between them
      "notes": {"50": "Pravila za količinu", "52": "..."}
    }
  }
}

Usage: python -I code_panels.py <spec.json> <out.json>
"""
import json
import re
import subprocess
import sys


def git(repo, *args):
    out = subprocess.run(['git', '-C', repo, *args], capture_output=True, check=True).stdout
    try:
        return out.decode('utf-8')
    except UnicodeDecodeError:
        return out.decode('cp1252', errors='replace')


def changed_lines(repo, base, head, path):
    diff = git(repo, 'diff', '-U0', '--no-color', '--no-ext-diff', base, head, '--', path)
    added, removed = set(), set()
    for m in re.finditer(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', diff, re.M):
        old_start, old_len = int(m.group(1)), int(m.group(2) or 1)
        new_start, new_len = int(m.group(3)), int(m.group(4) or 1)
        removed.update(range(old_start, old_start + old_len))
        added.update(range(new_start, new_start + new_len))
    return added, removed


def build(spec):
    repo, base, head = spec['repo'], spec['base'], spec['head']
    panels = {}
    for key, p in spec['panels'].items():
        side = p.get('side', 'head')
        sha = base if side == 'base' else head
        source = git(repo, 'show', f'{sha}:{p["file"]}').replace('\ufeff', '').replace('\t', '    ').split('\n')
        added, removed = changed_lines(repo, base, head, p['file'])
        marked = removed if side == 'base' else added
        kind_if_marked = 'del' if side == 'base' else 'add'
        notes = {int(k): v for k, v in p.get('notes', {}).items()}

        lines = []
        for i, (start, end) in enumerate(p['ranges']):
            if i:
                lines.append({'gap': True})
            for n in range(start, min(end, len(source)) + 1):
                lines.append({
                    'n': n,
                    'kind': kind_if_marked if n in marked else 'ctx',
                    'code': source[n - 1].rstrip(),
                    'note': notes.get(n, ''),
                })
        missing = [n for n in notes if not any(l.get('n') == n for l in lines)]
        if missing:
            raise SystemExit(f'{key}: notes on lines outside the ranges: {missing}')
        panels[key] = {'title': p['title'], 'sub': p.get('sub', ''), 'file': p['file'], 'side': side, 'lines': lines}
    return panels


if __name__ == '__main__':
    spec = json.load(open(sys.argv[1], encoding='utf-8'))
    panels = build(spec)
    json.dump(panels, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'panels={len(panels)} lines={sum(len(p["lines"]) for p in panels.values())}')
