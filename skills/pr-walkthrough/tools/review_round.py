"""Collects the threads the reviewer started or joined on a PR, for the "Što je riješeno" page of a second review round.

For every thread with a comment by the reviewer (`me` in the harvest) it records the comments in order, which of them came
after the reviewer's last word, whether the thread is resolved on the host, and whether the commits since the review touched
the commented lines (with the line moved to the new head). The judgement fields `outcome`, `why` and `reply` stay null for
Claude to fill in; running again keeps judgements already written for threads that did not get new comments or code changes.

Usage: python -I review_round.py <harvest.json> <repo> <reviewed head> <new head> <out round.json>
"""
import datetime
import json
import pathlib
import re
import subprocess
import sys

NEAR_LINES = 3
MAX_TEXT = 1500
MARKDOWN_ESCAPE = re.compile(r'\\([\\()\[\]_*`#.!-])')
MENTION = re.compile(r'@\{([^}]+)\}')
HUNK = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', re.M)
JUDGEMENT = ('outcome', 'why', 'reply', 'panel')

harvest_path, repo, old_head, new_head, out = sys.argv[1:6]
harvest = json.loads(pathlib.Path(harvest_path).read_text(encoding='utf-8-sig'))
me = harvest.get('me')


def git(*args):
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, encoding='utf-8').stdout


def when(value):
    text = str(value or '')
    for fmt in ('%m/%d/%Y %H:%M:%S', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S.%f%z'):
        try:
            parsed = datetime.datetime.strptime(text.replace('Z', '+00:00'), fmt)
            return parsed.replace(tzinfo=None) if parsed.tzinfo is None else parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        except ValueError:
            continue
    return datetime.datetime.min


def hunks(path):
    return [(int(a), int(b or 1), int(c), int(d or 1)) for a, b, c, d in HUNK.findall(git('diff', '-U0', old_head, new_head, '--', path))]


def follow_line(path, line):
    """The commented line at the new head, and whether the new commits changed code within a few lines of it."""
    if not path or not line:
        return None, False
    if subprocess.run(['git', '-C', repo, 'cat-file', '-e', f'{new_head}:{path}'], capture_output=True).returncode:
        return None, True
    offset, changed = 0, False
    for old_start, old_count, new_start, new_count in hunks(path):
        old_end = old_start + max(old_count, 1) - 1
        if old_end < line - NEAR_LINES:
            offset += new_count - old_count
            continue
        if old_start > line + NEAR_LINES:
            break
        changed = True
        if old_start <= line <= old_end:
            return new_start, True
        if old_end < line:
            offset += new_count - old_count
    return line + offset, changed


comments = harvest.get('comments') or []
by_id = {c['id']: c for c in comments if c.get('id') is not None}
name_by_account = {c['authorId']: c['author'] for c in comments if c.get('authorId')}


def readable(text):
    unescaped = MARKDOWN_ESCAPE.sub(r'\1', text or '')
    return MENTION.sub(lambda m: '@' + name_by_account.get(m.group(1), 'kolega'), unescaped)[:MAX_TEXT]


def root_of(comment):
    seen = set()
    while comment.get('replyTo') in by_id and comment['id'] not in seen:
        seen.add(comment['id'])
        comment = by_id[comment['replyTo']]
    return comment


threads = {}
for comment in sorted((c for c in comments if c.get('id') is not None), key=lambda c: when(c.get('created'))):
    threads.setdefault(root_of(comment)['id'], []).append(comment)

out_path = pathlib.Path(out)
earlier = json.loads(out_path.read_text(encoding='utf-8')) if out_path.exists() else {}
previous = {t['id']: t for t in earlier.get('threads', [])}

result = []
for root_id, items in threads.items():
    mine = [c for c in items if c.get('author') == me]
    if not mine:
        continue
    root = by_id[root_id]
    my_last = max(when(c.get('created')) for c in mine)
    head_line, code_changed = follow_line(root.get('path'), root.get('line'))
    entry = {
        'id': root_id, 'path': root.get('path'), 'line': root.get('line'), 'headLine': head_line,
        'resolved': any(c.get('resolved') for c in items), 'codeChanged': code_changed,
        'answered': any(c.get('author') != me and when(c.get('created')) > my_last for c in items),
        'comments': [{'id': c['id'], 'by': 'ti' if c.get('author') == me else c.get('author'), 'at': str(c.get('created') or ''),
                      'new': c.get('author') != me and when(c.get('created')) > my_last, 'text': readable(c.get('text'))} for c in items],
    }
    old = previous.get(root_id)
    unchanged = old and len(old.get('comments', [])) == len(entry['comments']) and old.get('codeChanged') == code_changed
    for key in JUDGEMENT:
        entry[key] = old.get(key) if unchanged else None
    result.append(entry)

result.sort(key=lambda t: (t['path'] is not None, t['path'] or '', t['line'] or 0))
round_data = {
    'from': old_head, 'to': new_head, 'author': harvest.get('author'), 'url': harvest.get('url'), 'host': harvest.get('host'),
    'commits': git('log', '--no-merges', '--format=%h %s', f'{old_head}..{new_head}').splitlines(),
    'summary': earlier.get('summary') if earlier.get('to') == new_head else None,
    'threads': result,
}
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(round_data, ensure_ascii=False, indent=1), encoding='utf-8', newline='\n')
answered = sum(t['answered'] for t in result)
changed = sum(t['codeChanged'] for t in result)
resolved = sum(t['resolved'] for t in result)
print(f'{out_path} (threads={len(result)}, answered={answered}, code changed={changed}, resolved={resolved}, commits={len(round_data["commits"])})')
