"""The PR's existing discussion for a walkthrough page, from the comments pr-review's harvest already read.

An inline comment starts a thread at its file and line; replies (replyTo, followed up to the first comment) join it.
Comments that are not inline, and their replies, are general comments on the PR. GitHub marks a comment outdated when its
line is from an older version of the file. Neither host's harvest says whether a thread is resolved, so none is.

Output (JSON): {"fetchedAt", "threads": [{id, path, line, side, outdated, resolved, url, comments: [{author, at, body}]}],
                "general": [{author, at, body, url, kind}]}

Usage: python -I pr_discussion.py <harvest.json> <out.json>
"""
import datetime
import json
import pathlib
import sys

POWERSHELL_DATE_FORMAT = '%m/%d/%Y %H:%M:%S'

harvest_path, out = sys.argv[1:3]
h = json.load(open(harvest_path, encoding='utf-8-sig'))
pr_url = h.get('url') or ''
is_github = h.get('host') == 'github'


def iso(value):
    text = str(value or '').strip()
    try:
        parsed = datetime.datetime.strptime(text, POWERSHELL_DATE_FORMAT)
    except ValueError:
        try:
            parsed = datetime.datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def comment_url(c):
    if not c.get('id'):
        return pr_url
    if is_github:
        return f"{pr_url}#discussion_r{c['id']}" if c.get('inline') else f"{pr_url}#issuecomment-{c['id']}"
    return f"{pr_url}#comment-{c['id']}"


comments = sorted(h.get('comments') or [], key=lambda c: iso(c.get('created')))
by_id = {c['id']: c for c in comments if c.get('id')}


def root_of(c):
    seen = set()
    while c.get('replyTo') in by_id and c['id'] not in seen:
        seen.add(c['id'])
        c = by_id[c['replyTo']]
    return c


threads, general, thread_by_root = [], [], {}
for c in comments:
    item = {'author': c.get('author') or '', 'at': iso(c.get('created')), 'body': c.get('text') or ''}
    root = root_of(c)
    if not root.get('inline') or not root.get('path'):
        general.append({**item, 'url': comment_url(c), 'kind': 'comment'})
        continue
    thread = thread_by_root.get(root['id'])
    if thread is None:
        thread = {'id': root['id'], 'path': root['path'], 'line': root.get('line') or 1, 'side': 'head',
                  'outdated': bool(root.get('outdated')), 'resolved': False, 'url': comment_url(root), 'comments': []}
        thread_by_root[root['id']] = thread
        threads.append(thread)
    thread['comments'].append(item)

fetched_at = datetime.datetime.fromtimestamp(pathlib.Path(harvest_path).stat().st_mtime, datetime.timezone.utc)
discussion = {'fetchedAt': fetched_at.strftime('%Y-%m-%dT%H:%M:%SZ'), 'threads': threads, 'general': general}
json.dump(discussion, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'threads={len(threads)} general={len(general)}')
