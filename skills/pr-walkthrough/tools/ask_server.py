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

It never writes to the PR: POST /discussion only reads a GitHub PR's threads again with the gh CLI.
"""
import argparse
import hmac
import http.server
import io
import json
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.parse

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
        self.proc = subprocess.Popen(args, cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

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

    def api(*args):
        r = subprocess.run([gh, 'api', *args], capture_output=True, text=True, encoding='utf-8', timeout=60)
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
        if self.path not in ('/ask', '/reset', '/history', '/discussion'):
            return self.reply(404, {'error': 'not found'})
        req = self.read_request()
        if req is None:
            return
        if self.path == '/discussion':
            found = github_discussion(req.get('slug'), req.get('number'))
            return self.reply(200 if found else 502, found or {'error': 'gh nije dostupan ili PR nije pronađen'})
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
