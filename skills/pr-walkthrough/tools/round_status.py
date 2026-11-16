"""Writes round-status.json, the short result of a second review round that the tray app reads to notify the user.

Usage: python -I round_status.py <round.json> <harvest.json> <page.html> <out round-status.json>
"""
import datetime
import json
import pathlib
import sys

FOR_ME = ('open', 'partly', 'answered')
OUTCOMES = ('open', 'partly', 'answered', 'waiting', 'fixed')

round_path, harvest_path, page, out = sys.argv[1:5]
round_data = json.loads(pathlib.Path(round_path).read_text(encoding='utf-8'))
harvest = json.loads(pathlib.Path(harvest_path).read_text(encoding='utf-8-sig'))

counts = {name: sum(1 for t in round_data['threads'] if t.get('outcome') == name) for name in OUTCOMES}
unjudged = sum(1 for t in round_data['threads'] if t.get('outcome') not in OUTCOMES)
comment_ids = [c['id'] for c in harvest.get('comments') or [] if isinstance(c.get('id'), int)]
status = {
    'repo': harvest.get('repo'), 'pr': harvest.get('pr'), 'author': harvest.get('author'),
    'head': round_data.get('to'), 'lastCommentId': max(comment_ids, default=None),
    'at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
    'page': str(pathlib.Path(page).resolve()),
    'forMe': sum(counts[name] for name in FOR_ME) + unjudged, 'counts': counts, 'unjudged': unjudged,
    'summary': round_data.get('summary'),
}
pathlib.Path(out).write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding='utf-8', newline='\n')
print(f'{out} (for me={status["forMe"]}, {counts}, unjudged={unjudged})')
