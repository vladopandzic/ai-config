"""Lets a walkthrough page ask the viewer's own Claude Code about the code, answering inside the page.

Run it in the folder of the repo the page is about; the answers are paid by whoever is logged in to that Claude Code:
    python pr-walkthrough-ask.py     (or: python pr-walkthrough-ask.py --repo <repo folder> --port 8799)

Each PR gets one Claude Code session that stays running (speed per question: "deep" = your own model and effort,
"fast" = --effort low, the default, "fastest" = Sonnet with --effort low): the first question brings the PR's overview with it, every later
question (from any part of the page) goes into the same conversation. The session id is kept in ~/.pr-walkthrough/sessions.json,
so after a restart the conversation continues. It listens on 127.0.0.1 only and needs the key it prints (kept in
~/.pr-walkthrough/ask-key, so it is typed into a page once). Claude runs with --restricted and only Read, Grep and Glob, confined
to a copy of the PR's code: the commit the page was made from is extracted from the repo's git (git archive) into
~/.pr-walkthrough/src/, so the answers are about the PR even when your checkout is on another branch; your checkout is never
touched. Without that commit locally it reads the repo folder. It can read the code, never change files or run commands. Answers stream back as JSON lines:
session, text, tool, done or error.

POST /discussion only reads a GitHub PR's threads again with the gh CLI.

POST /post sends the reviewer's own comments to the GitHub or Bitbucket PR, only when the reviewer clicks Send on the page:
GitHub through the gh CLI (the active account, or another logged-in account that sees the repo), inline comments as one review; Bitbucket with the same environment
variables as pr-review (BITBUCKET_<WORKSPACE>_EMAIL, reads with _TOKEN, writes only with _TOKEN_WRITE). Claude is not
involved. It first reports what is already on the PR, and refuses when the PR head moved past the page.
"""
import argparse
import base64
import hmac
import http.server
import io
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HOME = pathlib.Path.home() / '.pr-walkthrough'
KEY_FILE = HOME / 'ask-key'
SESSIONS_FILE = HOME / 'sessions.json'
SESSION_DIRS_FILE = HOME / 'session-dirs.json'
SOURCES_DIR = HOME / 'src'
KEEP_SOURCES = 6
SOURCE_READY_MARKER = '.pr-walkthrough-ok'
CLAUDE_ARGS = ['-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose', '--include-partial-messages',
               '--restricted', '--strict-mcp-config', '--tools', 'Read,Grep,Glob']
SPEEDS = {'deep': [], 'fast': ['--effort', 'low'], 'fastest': ['--model', 'sonnet', '--effort', 'low']}
# Without this a set ANTHROPIC_API_KEY makes claude -p bill API credits instead of the user's subscription.
CLAUDE_ENV = {name: value for name, value in os.environ.items() if name != 'ANTHROPIC_API_KEY'}


def load_key():
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding='utf-8').strip()
    HOME.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(8)
    KEY_FILE.write_text(key, encoding='utf-8')
    return key


def load_sessions():
    try:
        return json.loads(SESSIONS_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def pr_commit(repo, pr):
    short = str(pr).rsplit('@', 1)[-1] if '@' in str(pr) else ''
    if not re.fullmatch(r'[0-9a-f]{7,40}', short):
        return None
    r = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', '--quiet', f'{short}^{{commit}}'], capture_output=True, text=True, timeout=10)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def pr_source(repo, pr):
    """The PR's code at the tour's commit (the sha after @ in the PR key), extracted once into ~/.pr-walkthrough/src; None when
    that commit is not in the repo's git."""
    full = pr_commit(repo, pr)
    if not full:
        return None
    target = SOURCES_DIR / f'{repo.name}-{full[:12]}'
    if (target / SOURCE_READY_MARKER).exists():
        return target
    archive = subprocess.run(['git', '-C', str(repo), 'archive', '--format=tar', full], capture_output=True, timeout=300)
    if archive.returncode:
        return None
    tmp = target.with_name(target.name + '.tmp')
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(tmp, filter='data')
    except (OSError, tarfile.TarError):
        shutil.rmtree(tmp, ignore_errors=True)
        return None
    (tmp / SOURCE_READY_MARKER).write_text(full, encoding='utf-8')
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    old = sorted((d for d in SOURCES_DIR.iterdir() if d.is_dir() and (d / SOURCE_READY_MARKER).exists()), key=lambda d: d.stat().st_mtime, reverse=True)
    for d in old[KEEP_SOURCES:]:
        shutil.rmtree(d, ignore_errors=True)
    return target


def repo_slug(repo):
    r = subprocess.run(['git', '-C', str(repo), 'remote', 'get-url', 'origin'], capture_output=True, text=True, timeout=10)
    m = re.search(r'[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$', r.stdout.strip())
    return m.group(1).lower() if r.returncode == 0 and m else ''


def find_clone(slug, near):
    """The local clone of owner/name: the helper's own repo, or a folder next to it or one level further from it."""
    if repo_slug(near) == slug:
        return near
    folders = [d for r in (near.parent, near.parent.parent) for d in r.iterdir() if d.is_dir()]
    return next((d for d in folders if (d / '.git').exists() and repo_slug(d) == slug), None)


def git_head(repo):
    try:
        return subprocess.run(['git', '-C', str(repo), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def git_ahead(repo, branch, tour_head):
    """How far origin/<branch> (as last fetched) is ahead of the commit the tour was made for: (short sha, commits) or None."""
    if not branch or not tour_head:
        return None
    ref = f'refs/remotes/origin/{branch}'
    run = lambda *a: subprocess.run(['git', '-C', str(repo), *a], capture_output=True, text=True, timeout=10)
    try:
        remote = run('rev-parse', '--short', '--verify', '--quiet', ref).stdout.strip()
        if not remote:
            return None
        ahead = run('rev-list', '--count', f'{tour_head}..{ref}')
        return remote, int(ahead.stdout.strip()) if ahead.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def events(o):
    kind = o.get('type')
    if kind == 'stream_event':
        e = o.get('event') or {}
        if e.get('type') == 'content_block_delta' and (e.get('delta') or {}).get('type') == 'text_delta':
            yield {'t': 'text', 'd': e['delta']['text']}
    elif kind == 'assistant':
        for c in (o.get('message') or {}).get('content') or []:
            if c.get('type') == 'tool_use':
                args = c.get('input') or {}
                name = c.get('name')
                target = pathlib.PurePath(args['file_path']).name if args.get('file_path') else args.get('pattern') or ''
                yield {'t': 'tool', 'name': name, 'target': target, 'd': f'{name} {target}'.strip()}
    elif kind == 'result' and o.get('is_error'):
        yield {'t': 'error', 'm': o.get('result') or 'Claude nije odgovorio.'}


class PrSession:
    """One running Claude Code conversation about one PR; questions take turns."""

    def __init__(self, server, pr):
        self.server, self.pr = server, pr
        self.lock = threading.Lock()
        self.proc = None
        self.cwd = None
        self.speed = None
        self.sid = server.sessions.get(pr)
        self.turns = 0

    def start(self, base, speed):
        if self.proc and self.proc.poll() is None and speed == self.speed:
            return
        # Another speed needs another process; the conversation carries on through --resume.
        self.stop()
        self.speed = speed
        args = [self.server.claude, *CLAUDE_ARGS, *SPEEDS.get(speed, [])]
        if self.sid:
            args += ['--resume', self.sid]
        elif base:
            args += ['--resume', base, '--fork-session']
        # A conversation can only be resumed from the folder it started in, so an older one keeps the repo folder.
        if self.sid:
            self.cwd = pathlib.Path(self.server.session_dirs.get(self.sid) or self.server.repo)
        else:
            repo = self.server.repo_for(self.pr)
            self.cwd = pr_source(repo, self.pr) or repo
        self.proc = subprocess.Popen(args, cwd=self.cwd, env=CLAUDE_ENV, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    def ask(self, text, base, speed, emit):
        """Sends one question and passes its events to emit; a failed emit (the page went away) stops the turn."""
        fresh = not self.sid
        self.start(base, speed if speed in SPEEDS else 'fast')
        emit({'t': 'session', 'id': self.sid, 'fresh': fresh, 'turn': self.turns + 1})
        self.proc.stdin.write((json.dumps({'type': 'user', 'message': {'role': 'user', 'content': text}}) + '\n').encode('utf-8'))
        self.proc.stdin.flush()
        for raw in self.proc.stdout:
            try:
                o = json.loads(raw)
            except ValueError:
                continue
            if o.get('session_id') and o['session_id'] != self.sid:
                self.sid = o['session_id']
                self.server.remember(self.pr, self.sid, self.cwd)
            for ev in events(o):
                emit(ev)
            if o.get('type') == 'result':
                self.turns += 1
                emit({'t': 'done', 'session': self.sid, 'turn': self.turns})
                return
        self.stop()
        emit({'t': 'error', 'm': 'Claude je stao. Pitaj ponovno; ako se ponavlja, pokreni novu sesiju (⚙).'})

    def reset(self):
        self.stop()
        self.sid, self.turns = None, 0
        self.server.remember(self.pr, None)


QUESTION_FILE = re.compile(r'^Fajl: (.+?) \((.+?)\), linije (\d+)–(\d+)(?:, (.+))?$', re.M)
SAME_CODE = '(Isti kod kao maloprije.) '


GH_THREADS = """query($o: String!, $r: String!, $n: Int!) { repository(owner: $o, name: $r) { pullRequest(number: $n) {
  reviewThreads(first: 100) { nodes { isResolved isOutdated comments(first: 1) { nodes { databaseId } } } } } } }"""


def github_discussion(slug, number):
    """The PR's review threads (with replies, resolved / outdated), conversation comments and review notes, read with the gh CLI."""
    gh = shutil.which('gh')
    if not gh or not re.fullmatch(r'[\w.-]+/[\w.-]+', str(slug or '')) or not str(number).isdigit():
        return None

    env = _gh_env(slug)

    def api(*args):
        r = subprocess.run([gh, 'api', *args], capture_output=True, text=True, encoding='utf-8', env=env, timeout=60)
        return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None

    def pages(path):
        out = []
        for page in range(1, 20):
            chunk = api(f'{path}?per_page=100&page={page}') or []
            out += chunk
            if len(chunk) < 100:
                return out
        return out

    raw = pages(f'repos/{slug}/pulls/{number}/comments')
    owner, name = slug.split('/')
    states = {}
    graph = api('graphql', '-f', f'query={GH_THREADS}', '-F', f'o={owner}', '-F', f'r={name}', '-F', f'n={number}')
    for t in ((((graph or {}).get('data') or {}).get('repository') or {}).get('pullRequest') or {}).get('reviewThreads', {}).get('nodes', []):
        first = (t.get('comments') or {}).get('nodes') or []
        if first:
            states[first[0]['databaseId']] = t
    threads, by_root = [], {}
    for c in sorted(raw, key=lambda c: c['created_at']):
        root = c.get('in_reply_to_id') or c['id']
        item = {'author': c['user']['login'], 'at': c['created_at'], 'body': c['body'], 'url': c['html_url']}
        if root in by_root:
            by_root[root]['comments'].append(item)
            continue
        st = states.get(c['id'], {})
        t = {'id': c['id'], 'path': c['path'], 'line': c.get('line') or c.get('original_line') or 1, 'side': 'base' if c.get('side') == 'LEFT' else 'head',
             'outdated': bool(st.get('isOutdated', c.get('line') is None)), 'resolved': bool(st.get('isResolved')), 'url': c['html_url'], 'comments': [item]}
        by_root[c['id']] = t
        threads.append(t)
    general = [{'author': c['user']['login'], 'at': c['created_at'], 'body': c['body'], 'url': c['html_url'], 'kind': 'comment'}
               for c in pages(f'repos/{slug}/issues/{number}/comments')]
    general += [{'author': r['user']['login'], 'at': r['submitted_at'], 'body': r['body'], 'url': r['html_url'], 'kind': 'review', 'state': r['state']}
                for r in pages(f'repos/{slug}/pulls/{number}/reviews') if r.get('submitted_at') and (r.get('body') or r['state'] in ('APPROVED', 'CHANGES_REQUESTED'))]
    general.sort(key=lambda g: g['at'])
    return {'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'threads': threads, 'general': general}


def history(sid):
    """The questions and answers of a PR session, read from Claude Code's own transcript, grouped by the code they were about."""
    found = list((pathlib.Path.home() / '.claude' / 'projects').glob(f'*/{sid}.jsonl')) if sid else []
    if not found:
        return []
    items, cur, turn = [], None, None
    for line in found[0].read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        content = (o.get('message') or {}).get('content')
        if o.get('type') == 'user' and isinstance(content, str):
            q = content[content.rfind('Pitanje:') + len('Pitanje:'):].strip() if 'Pitanje:' in content else content.strip()
            m = QUESTION_FILE.search(content)
            if m:
                cur = {'file': m.group(1), 'side': 'base' if m.group(2).startswith('stari kod') else 'head',
                       'from': int(m.group(3)), 'to': int(m.group(4)), 'member': (m.group(5) or '').split('\n')[0] or None, 'turns': []}
                items.append(cur)
            elif not cur:
                continue
            turn = {'q': q.removeprefix(SAME_CODE), 'a': '', 'at': o.get('timestamp', '')}
            cur['turns'].append(turn)
        elif o.get('type') == 'assistant' and turn is not None and isinstance(content, list):
            text = '\n\n'.join(c.get('text', '') for c in content if c.get('type') == 'text').strip()
            if text:
                turn['a'] = (turn['a'] + '\n\n' + text).strip()
    for it in items:
        it['turns'] = [t for t in it['turns'] if t['a']]
    return [it for it in items if it['turns']]


class Server(http.server.ThreadingHTTPServer):
    def __init__(self, port, repo, claude):
        super().__init__(('127.0.0.1', port), Handler)
        self.repo, self.claude, self.key = repo, claude, load_key()
        self.sessions = load_sessions()
        try:
            self.session_dirs = json.loads(SESSION_DIRS_FILE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.session_dirs = {}
        self.clones = {}
        self.live = {}
        self.guard = threading.Lock()

    def session(self, pr):
        with self.guard:
            return self.live.setdefault(pr, PrSession(self, pr))

    def repo_for(self, pr):
        """The clone of the repo in the PR key (owner/name#n@sha), so one helper serves pages of different repos."""
        slug = str(pr).split('#', 1)[0].lower()
        if slug not in self.clones:
            try:
                self.clones[slug] = find_clone(slug, self.repo)
            except (OSError, subprocess.SubprocessError):
                self.clones[slug] = None
        return self.clones[slug] or self.repo

    def remember(self, pr, sid, cwd=None):
        with self.guard:
            if sid:
                self.sessions[pr] = sid
                if cwd:
                    self.session_dirs[sid] = str(cwd)
            else:
                self.sessions.pop(pr, None)
            HOME.mkdir(parents=True, exist_ok=True)
            SESSIONS_FILE.write_text(json.dumps(self.sessions, indent=1), encoding='utf-8')
            SESSION_DIRS_FILE.write_text(json.dumps(self.session_dirs, indent=1), encoding='utf-8')


_GH_ENV_BY_REPO = {}
GITHUB_REVIEW_EVENTS = {'comment': 'COMMENT', 'changes': 'REQUEST_CHANGES', 'approve': 'APPROVE'}
BITBUCKET_REVIEW_PATHS = {'changes': 'request-changes', 'approve': 'approve'}


def _gh_env(slug):
    """gh's environment for a repo: the active account when it sees the repo, otherwise the first other account gh is logged in
    to that does (a work and a private account side by side). None means the active account."""
    if slug in _GH_ENV_BY_REPO:
        return _GH_ENV_BY_REPO[slug]
    gh = shutil.which('gh')
    sees_repo = lambda env: subprocess.run([gh, 'api', f'repos/{slug}', '--silent'], capture_output=True, env=env, timeout=60).returncode == 0
    if sees_repo(None):
        _GH_ENV_BY_REPO[slug] = None
        return None
    status = subprocess.run([gh, 'auth', 'status', '--hostname', 'github.com'], capture_output=True, text=True, encoding='utf-8', timeout=30)
    for account in re.findall(r'account (\S+)', status.stdout + status.stderr):
        token = subprocess.run([gh, 'auth', 'token', '--hostname', 'github.com', '--user', account], capture_output=True, text=True,
                               encoding='utf-8', timeout=30).stdout.strip()
        env = {**os.environ, 'GH_TOKEN': token}
        if token and sees_repo(env):
            _GH_ENV_BY_REPO[slug] = env
            return env
    return None


def _gh(env, *args, payload=None):
    gh = shutil.which('gh')
    r = subprocess.run([gh, 'api', *args, *(['--input', '-'] if payload is not None else [])], capture_output=True, text=True, encoding='utf-8',
                       input=json.dumps(payload) if payload is not None else None, env=env, timeout=60)
    try:
        body = json.loads(r.stdout) if r.stdout.strip() else None
    except ValueError:
        body = None
    return r.returncode == 0, body, (r.stderr or r.stdout).strip()[:300]


def _gh_pages(env, path):
    out = []
    for page in range(1, 20):
        ok, chunk, _ = _gh(env, f'{path}?per_page=100&page={page}')
        chunk = chunk if ok and isinstance(chunk, list) else []
        out += chunk
        if len(chunk) < 100:
            return out
    return out


def _same(a, b):
    return ' '.join(str(a or '').split()) == ' '.join(str(b or '').split())


def github_post(slug, number, head, items, dry, review=None):
    """What of the tour's comments is already on the PR (dry), or send the given ones. Items: key, kind inline|reply|general,
    path, line, side LEFT|RIGHT, body, replyTo. review = {event comment|changes|approve, body} is submitted after the items,
    which is what clears the author's review request."""
    if not shutil.which('gh') or not re.fullmatch(r'[\w.-]+/[\w.-]+', str(slug or '')) or not str(number).isdigit():
        return None
    env = _gh_env(slug)
    ok, pr, err = _gh(env, f'repos/{slug}/pulls/{number}')
    if not ok:
        return {'error': f'PR nije dohvaćen: {err}'}
    pr_head = pr['head']['sha']
    login = (_gh(env, 'user')[1] or {}).get('login', '?')
    result = {'login': login, 'head': pr_head, 'moved': bool(head) and not pr_head.startswith(str(head)),
              'reviewRequested': any(u.get('login') == login for u in pr.get('requested_reviewers') or [])}
    threads = _gh_pages(env, f'repos/{slug}/pulls/{number}/comments')
    general = _gh_pages(env, f'repos/{slug}/issues/{number}/comments')
    mine = [c for c in threads if c['user']['login'] == login]
    resolved_threads = github_resolved_threads(env, slug, number) if any(it.get('kind') == 'reply' for it in items) else {}
    status = {}
    for it in items:
        k, body = it.get('key'), it.get('body')
        if it.get('kind') == 'reply':
            found = next((c for c in mine if (c.get('in_reply_to_id') or c['id']) == it.get('replyTo') and _same(c['body'], body)), None)
            there = False
        elif it.get('kind') == 'general':
            found = next((c for c in general if c['user']['login'] == login and _same(c['body'], body)), None)
            there = False
        else:
            at = [c for c in mine if c['path'] == it.get('path') and (c.get('line') or c.get('original_line')) == it.get('line')]
            found = next((c for c in at if _same(c['body'], body)), None)
            there = bool(at)
        status[k] = {'status': 'posted', 'id': found['id'], 'url': found['html_url']} if found else {'status': 'mine-there' if there else 'new'}
    if dry or result['moved']:
        result['items'] = status
        return result
    sent = {}

    def done(it, c):
        sent[it['key']] = {'status': 'sent', 'id': c['id'], 'url': c['html_url']}

    todo = [it for it in items if status.get(it.get('key'), {}).get('status') != 'posted']
    inline = [it for it in todo if it.get('kind') == 'inline']
    if inline:
        ok, rv, err = _gh(env, '-X', 'POST', f'repos/{slug}/pulls/{number}/reviews', payload={
            'commit_id': pr_head, 'event': 'COMMENT', 'body': '',
            'comments': [{'path': it['path'], 'line': it['line'], 'side': it.get('side') or 'RIGHT', 'body': it['body']} for it in inline]})
        if ok:
            created = _gh_pages(env, f"repos/{slug}/pulls/{number}/reviews/{rv['id']}/comments")
            for it in inline:
                c = next((c for c in created if c['path'] == it['path'] and _same(c['body'], it['body'])), None)
                if c:
                    done(it, c)
                else:
                    sent[it['key']] = {'status': 'error', 'error': 'poslano, ali komentar nije pronađen u reviewu'}
        else:
            for it in inline:
                ok, c, err = _gh(env, '-X', 'POST', f'repos/{slug}/pulls/{number}/comments', payload={
                    'commit_id': pr_head, 'path': it['path'], 'line': it['line'], 'side': it.get('side') or 'RIGHT', 'body': it['body']})
                if ok:
                    done(it, c)
                else:
                    sent[it['key']] = {'status': 'error', 'error': err}
    for it in todo:
        if it.get('kind') == 'reply':
            ok, c, err = _gh(env, '-X', 'POST', f"repos/{slug}/pulls/{number}/comments/{int(it['replyTo'])}/replies", payload={'body': it['body']})
            thread_id = resolved_threads.get(int(it['replyTo']))
            if ok and thread_id:
                reopened, _, reopen_err = _gh(env, 'graphql', '-f', 'query=mutation($t: ID!) { unresolveReviewThread(input: { threadId: $t }) { thread { isResolved } } }', '-F', f't={thread_id}')
                done(it, c)
                sent[it['key']]['reopened'] = reopened
                if not reopened:
                    sent[it['key']]['warning'] = f'nit nije ponovno otvorena: {reopen_err}'
                continue
        elif it.get('kind') == 'general':
            ok, c, err = _gh(env, '-X', 'POST', f'repos/{slug}/issues/{number}/comments', payload={'body': it['body']})
        else:
            continue
        if ok:
            done(it, c)
        else:
            sent[it['key']] = {'status': 'error', 'error': err}
    result['items'] = {**{k: v for k, v in status.items() if v['status'] == 'posted'}, **sent}
    if review:
        ok, rv, err = _gh(env, '-X', 'POST', f'repos/{slug}/pulls/{number}/reviews', payload={
            'commit_id': pr_head, 'event': GITHUB_REVIEW_EVENTS[review['event']], 'body': review['body']})
        result['review'] = {'status': 'sent', 'url': rv.get('html_url', '')} if ok else {'status': 'error', 'error': err}
    return result


def github_resolved_threads(env, slug, number):
    """Resolved review threads of the PR: the id of each thread's first comment -> the thread's node id."""
    owner, name = slug.split('/', 1)
    query = ('query($o: String!, $r: String!, $n: Int!) { repository(owner: $o, name: $r) { pullRequest(number: $n) { '
             'reviewThreads(first: 100) { nodes { id isResolved comments(first: 1) { nodes { databaseId } } } } } } }')
    ok, body, _ = _gh(env, 'graphql', '-f', f'query={query}', '-F', f'o={owner}', '-F', f'r={name}', '-F', f'n={number}')
    nodes = (((body or {}).get('data') or {}).get('repository') or {}).get('pullRequest', {}).get('reviewThreads', {}).get('nodes', []) if ok else []
    return {n['comments']['nodes'][0]['databaseId']: n['id'] for n in nodes if n.get('isResolved') and n['comments']['nodes']}


def bitbucket_thread_root(comments, comment_id):
    by_id = {c['id']: c for c in comments}
    root = by_id.get(comment_id)
    while root and (root.get('parent') or {}).get('id') in by_id:
        root = by_id[root['parent']['id']]
    return root


BITBUCKET_API = 'https://api.bitbucket.org/2.0'


def environment_value(name):
    """A process variable, else on Windows the user's saved one, so a helper started before the variable was set still finds it."""
    value = os.environ.get(name)
    if value or sys.platform != 'win32':
        return value
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def _bb(slug, path, write=False, payload=None, method=None):
    """One Bitbucket API call: (ok, data, error). Reads with the workspace's read token, writes only with its write token."""
    ws = re.sub(r'\W', '_', slug.split('/')[0]).upper()
    email = environment_value(f'BITBUCKET_{ws}_EMAIL')
    token = environment_value(f'BITBUCKET_{ws}_TOKEN_WRITE') if write else environment_value(f'BITBUCKET_{ws}_TOKEN') or environment_value(f'BITBUCKET_{ws}_TOKEN_WRITE')
    if not email or not token:
        return False, None, f"nema tokena BITBUCKET_{ws}_EMAIL / BITBUCKET_{ws}_{'TOKEN_WRITE' if write else 'TOKEN'}"
    url = path if path.startswith(BITBUCKET_API) else BITBUCKET_API + (path if path.startswith('/') else f'/repositories/{slug}/{path}')
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8') if payload is not None else None, method=method or ('POST' if payload is not None else 'GET'))
    req.add_header('Authorization', 'Basic ' + base64.b64encode(f'{email}:{token}'.encode('utf-8')).decode('ascii'))
    req.add_header('Accept', 'application/json')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return True, json.loads(r.read().decode('utf-8').strip() or '{}'), ''
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode('utf-8'))['error']['message']
        except (ValueError, KeyError, TypeError, OSError):
            detail = ''
        return False, None, f'HTTP {e.code} {detail}'.strip()
    except OSError as e:
        return False, None, str(e)


def _bb_pages(slug, path):
    out, ok, err = [], True, ''
    while path and ok:
        ok, page, err = _bb(slug, path)
        if ok:
            out += page.get('values', [])
            path = page.get('next')
    return out, err


def bitbucket_post(slug, number, head, items, dry, review=None):
    """github_post for Bitbucket: same items, same answer. A comment goes out one by one, each with its own result. The review
    becomes an approval or a change request, and its text a general comment."""
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', str(slug or '')) or not str(number).isdigit():
        return None
    ok, pr, err = _bb(slug, f'pullrequests/{number}')
    if not ok:
        return {'error': f'PR nije dohvaćen: {err}'}
    pr_head = pr['source']['commit']['hash']
    me = (_bb(slug, '/user')[1] or {})
    result = {'login': me.get('display_name') or 'vlasnik tokena', 'head': pr_head, 'moved': bool(head) and not (str(head).startswith(pr_head) or pr_head.startswith(str(head)))}
    comments, err = _bb_pages(slug, f'pullrequests/{number}/comments?pagelen=100')
    if err:
        return {'error': f'Komentari nisu dohvaćeni: {err}'}
    comments = [c for c in comments if not c.get('deleted')]
    mine = [c for c in comments if not me.get('account_id') or (c.get('user') or {}).get('account_id') == me['account_id']]
    text = lambda c: (c.get('content') or {}).get('raw', '')
    url = lambda c: ((c.get('links') or {}).get('html') or {}).get('href', '')

    def inline_at(c, it):
        at = c.get('inline') or {}
        return at.get('path') == it.get('path') and at.get('from' if it.get('side') == 'LEFT' else 'to') == it.get('line')

    status = {}
    for it in items:
        k, body = it.get('key'), it.get('body')
        if it.get('kind') == 'reply':
            at = [c for c in mine if (c.get('parent') or {}).get('id') == it.get('replyTo')]
        elif it.get('kind') == 'general':
            at = [c for c in mine if not c.get('inline') and not c.get('parent')]
        else:
            at = [c for c in mine if inline_at(c, it)]
        found = next((c for c in at if _same(text(c), body)), None)
        status[k] = {'status': 'posted', 'id': found['id'], 'url': url(found)} if found else {'status': 'mine-there' if at and me.get('account_id') and it.get('kind') == 'inline' else 'new'}
    if dry or result['moved']:
        result['items'] = status
        return result
    sent = {}
    for it in items:
        if status.get(it.get('key'), {}).get('status') == 'posted':
            continue
        payload = {'content': {'raw': it['body']}}
        if it.get('kind') == 'reply':
            payload['parent'] = {'id': int(it['replyTo'])}
        elif it.get('kind') != 'general':
            payload['inline'] = {'path': it['path'], 'from' if it.get('side') == 'LEFT' else 'to': it['line']}
        ok, c, err = _bb(slug, f'pullrequests/{number}/comments', write=True, payload=payload)
        if ok:
            sent[it['key']] = {'status': 'sent', 'id': c['id'], 'url': url(c)}
            root = bitbucket_thread_root(comments, int(it['replyTo'])) if it.get('kind') == 'reply' else None
            if root and root.get('resolution') is not None:
                reopened, _, reopen_err = _bb(slug, f"pullrequests/{number}/comments/{root['id']}/resolve", write=True, method='DELETE')
                sent[it['key']]['reopened'] = reopened
                if not reopened:
                    sent[it['key']]['warning'] = f'nit nije ponovno otvorena: {reopen_err}'
        else:
            sent[it['key']] = {'status': 'error', 'error': err}
    result['items'] = {**{k: v for k, v in status.items() if v['status'] == 'posted'}, **sent}
    if review:
        ok, err = True, ''
        if review['body']:
            ok, _, err = _bb(slug, f'pullrequests/{number}/comments', write=True, payload={'content': {'raw': review['body']}})
        if ok and review['event'] in BITBUCKET_REVIEW_PATHS:
            ok, _, err = _bb(slug, f"pullrequests/{number}/{BITBUCKET_REVIEW_PATHS[review['event']]}", write=True, payload={})
        result['review'] = {'status': 'sent', 'url': ((pr.get('links') or {}).get('html') or {}).get('href', '')} if ok else {'status': 'error', 'error': err}
    return result


def review_request(raw):
    """The review the page asks to submit with the comments, or None. Comment and change request need a text."""
    if not isinstance(raw, dict) or raw.get('event') not in GITHUB_REVIEW_EVENTS:
        return None
    body = str(raw.get('body') or '').strip()
    if raw['event'] != 'approve' and not body:
        return None
    return {'event': raw['event'], 'body': body}


class Handler(http.server.BaseHTTPRequestHandler):
    def cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Private-Network', 'true')

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path != '/ping':
            return self.reply(404, {'error': 'not found'})
        q = urllib.parse.parse_qs(url.query)
        branch, tour_head = q.get('branch', [''])[0], q.get('head', [''])[0]
        pr = q.get('pr', [''])[0]
        repo = self.server.repo_for(pr) if pr else self.server.repo
        body = {'ok': True, 'repo': repo.name, 'head': git_head(repo)}
        if pr:
            sid = self.server.sessions.get(pr)
            body['prCommit'] = bool(pr_commit(repo, pr))
            body['prSource'] = SOURCES_DIR in pathlib.Path(self.server.session_dirs.get(sid, str(self.server.repo))).parents if sid else body['prCommit']
            body['clone'] = bool(self.server.clones.get(pr.split('#', 1)[0].lower()))
        if all(c.isalnum() or c in '._-/' for c in branch) and all(c in '0123456789abcdef' for c in tour_head.lower()):
            found = git_ahead(repo, branch, tour_head)
            if found:
                body['remote'], body['ahead'] = found
        self.reply(200, body)

    def read_request(self):
        try:
            req = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        except ValueError:
            self.reply(400, {'error': 'bad request'})
            return None
        if not hmac.compare_digest(str(req.get('key', '')), self.server.key):
            self.reply(403, {'error': 'wrong key'})
            return None
        if not str(req.get('pr') or '').strip():
            self.reply(400, {'error': 'missing pr'})
            return None
        return req

    def do_POST(self):
        if self.path not in ('/ask', '/reset', '/history', '/discussion', '/post'):
            return self.reply(404, {'error': 'not found'})
        req = self.read_request()
        if req is None:
            return
        if self.path == '/discussion':
            found = github_discussion(req.get('slug'), req.get('number'))
            return self.reply(200 if found else 502, found or {'error': 'gh nije dostupan ili PR nije pronađen'})
        if self.path == '/post':
            items = [it for it in (req.get('items') or []) if isinstance(it, dict) and str(it.get('body') or '').strip()]
            post = bitbucket_post if req.get('host') == 'bitbucket' else github_post
            found = post(req.get('slug'), req.get('number'), str(req.get('head') or ''), items, bool(req.get('dry')), review_request(req.get('review')))
            return self.reply(200 if found and not found.get('error') else 502, found or {'error': 'gh nije dostupan ili PR nije pronađen'})
        if self.path == '/history':
            return self.reply(200, {'items': history(self.server.sessions.get(str(req['pr'])))})
        session = self.server.session(str(req['pr']))
        if self.path == '/reset':
            with session.lock:
                session.reset()
            return self.reply(200, {'ok': True})

        prompt = str(req.get('prompt') or '').strip()
        if not prompt:
            return self.reply(400, {'error': 'empty prompt'})
        self.send_response(200)
        self.cors()
        self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

        def emit(ev):
            self.wfile.write((json.dumps(ev, ensure_ascii=False) + '\n').encode('utf-8'))
            self.wfile.flush()

        with session.lock:
            text = prompt if session.sid else f"{str(req.get('prime') or '').strip()}\n\n{prompt}".strip()
            try:
                session.ask(text, str(req.get('base') or '').strip(), str(req.get('speed') or ''), emit)
            except (BrokenPipeError, ConnectionResetError, OSError):
                session.stop()

    def log_message(self, fmt, *args):
        pass


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description='PR walkthrough → lokalni Claude Code')
    ap.add_argument('--repo', default='.', help='folder repoa (zadano: trenutni)')
    ap.add_argument('--port', type=int, default=8799)
    a = ap.parse_args()
    claude = shutil.which('claude')
    if not claude:
        sys.exit('Claude Code (naredba "claude") nije instaliran ili nije u PATH-u.')
    repo = pathlib.Path(a.repo).resolve()
    if not (repo / '.git').exists():
        sys.exit(f'{repo} nije git repo. Pokreni ovo u folderu repoa ili dodaj --repo <folder>.')
    server = Server(a.port, repo, claude)
    print(f'PR walkthrough pomoćnik: {repo.name} @ {git_head(repo) or "?"} na http://127.0.0.1:{a.port}')
    print(f'Ključ (upiši u stranicu jednom): {server.key}')
    print('Ctrl+C za kraj.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for s in server.live.values():
            s.stop()


if __name__ == '__main__':
    main()
