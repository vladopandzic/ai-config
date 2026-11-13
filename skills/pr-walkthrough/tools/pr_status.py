"""PR status for the dashboard at the top of a walkthrough page: state, approvals, CI, comments, previous review, size.

Reads the JSON that pr-review's pr-harvest.ps1 prints. The reviewer the harvest calls `me` (and `git config user.name`)
becomes "ti", so the page never carries the user's own name; other reviewers keep theirs (they are part of the PR, like
the author).

Usage: python -I pr_status.py <repo> <base> <head> <harvest.json> <out.json>
"""
import datetime
import json
import pathlib
import re
import subprocess
import sys

YOU = 'ti'

repo, base, head, harvest_path, out = sys.argv[1:6]


def git(*args):
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.strip()


h = json.load(open(harvest_path, encoding='utf-8-sig'))
me = {name.casefold() for name in (h.get('me'), git('config', 'user.name')) if name}

stat = git('diff', '--shortstat', base, head)
numbers = {k: int(v) for v, k in re.findall(r'(\d+) (file|insertion|deletion)', stat)}
commits = int(git('rev-list', '--count', f'{base}..{head}') or 0)

author = (h.get('author') or '').casefold()
reviewers = {}
for a in h.get('approvals') or []:
    if a.get('name', '').casefold() == author:
        continue
    name = YOU if a.get('name', '').casefold() in me else a.get('name', '')
    reviewers[name] = reviewers.get(name, False) or bool(a.get('approved'))
approvals = [{'name': name, 'approved': ok} for name, ok in reviewers.items()]
approvals.sort(key=lambda a: (a['name'] != YOU, not a['approved']))

prev = h.get('previousReview') or {}
previous = None
if prev.get('at'):
    previous = {'at': prev['at'][:10], 'myComments': len(prev.get('myCommentIds') or []),
                'newCommits': len(prev.get('commitsSince') or []), 'changedFiles': len(prev.get('changedFiles') or [])}

status = {
    'at': datetime.datetime.fromtimestamp(pathlib.Path(harvest_path).stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
    'state': h.get('state', ''),
    'author': h.get('author', ''),
    'source': h.get('source', ''), 'dest': h.get('dest', ''),
    'approvals': approvals,
    'ci': [{'state': c.get('state', ''), 'name': c.get('name', '')} for c in h.get('ci') or []],
    'comments': len(h.get('comments') or []),
    'previousReview': previous,
    'files': numbers.get('file', 0), 'added': numbers.get('insertion', 0), 'removed': numbers.get('deletion', 0),
    'commits': commits,
}
json.dump(status, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"state={status['state']} approvals={sum(a['approved'] for a in approvals)}/{len(approvals)} "
      f"ci={[c['state'] for c in status['ci']]} comments={status['comments']} files={status['files']} +{status['added']}/-{status['removed']}")
