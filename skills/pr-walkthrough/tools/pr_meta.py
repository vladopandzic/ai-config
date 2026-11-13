"""Links for a walkthrough page: the PR, its commits, and every file the page shows, so each one opens the right place.

The host (GitHub, Bitbucket Cloud or Azure DevOps, cloud or Server) and owner/repo come from `git remote get-url origin`
when <owner/name> is "auto"; for Azure DevOps that is <project>/<repo>.
Per file the page gets URL templates it fills with line numbers:
  diff              the file in the PR's diff
  diffLineNew/Old   one line in the PR's diff, new (PR) side / old side   -> {a}
  diffRangeNew/Old  a range of lines in the PR's diff                    -> {a} {b}
  blobHead/BaseRange  the whole file at the PR's head / base commit, lines {a}-{b} highlighted
Bitbucket's PR diff has no range anchor, so its "range" opens the first line; Azure DevOps's PR diff has no line anchor at
all, so its diff links open the file in the PR.

Usage: python -I pr_meta.py <repo_dir> <owner/name|auto> <pr_number|-> <base> <head> <out.json> [code-panels.json] [topics.json]
       <pr_number> "-" = no PR yet: links go to the compare view.
"""
import hashlib
import json
import re
import subprocess
import sys
import urllib.parse

repo_dir, slug, pr, base, head, out, *sources = sys.argv[1:]


def git(*args):
    return subprocess.run(['git', '-C', repo_dir, *args], capture_output=True, check=True).stdout.decode('utf-8', 'replace')


def azure_repo_url(remote):
    """The web URL of an Azure DevOps repo (cloud, visualstudio.com or Server) from its https or ssh remote, or None."""
    ssh_cloud = re.match(r'^(?:ssh://)?[^@/]+@ssh\.dev\.azure\.com(?::22)?[:/]v3/([^/]+)/([^/]+)/([^/]+?)/?$', remote)
    if ssh_cloud:
        org, project, name = ssh_cloud.groups()
        return f'https://dev.azure.com/{org}/{project}/_git/{name}'
    web = re.match(r'^(?:https?|ssh)://(?:[^@/]+@)?([^/:]+)(?::\d+)?(/.*?/_git/[^/]+?)/?$', remote)
    if not web:
        return None
    server, path = web.groups()
    if server.startswith('ssh.'):
        server = server[len('ssh.'):]
    return f'https://{server}{path}'


remote = git('remote', 'get-url', 'origin').strip()
m = re.search(r'(github\.com|bitbucket\.org)[:/]+([^/]+)/([^/]+?)(?:\.git)?$', remote)
azure_url = None if m else azure_repo_url(remote)
if m:
    host = 'github' if m.group(1) == 'github.com' else 'bitbucket'
    remote_slug = f'{m.group(2)}/{m.group(3)}'
elif azure_url:
    host = 'azure'
    project_and_repo = re.search(r'/([^/]+)/_git/([^/]+)$', azure_url)
    remote_slug = '/'.join(urllib.parse.unquote(part) for part in project_and_repo.groups())
else:
    raise SystemExit(f'Unknown git host in remote {remote!r}: add its URL formats here.')
if slug == 'auto':
    slug = remote_slug

base_sha = git('rev-parse', base).strip()
head_sha = git('rev-parse', head).strip()
has_pr = pr != '-'

if host == 'github':
    repo_url = f'https://github.com/{slug}'
    pr_url = f'{repo_url}/pull/{pr}' if has_pr else f'{repo_url}/compare/{base_sha}...{head_sha}'
    files_url = f'{pr_url}/files' if has_pr else pr_url
    commits_url = f'{pr_url}/commits' if has_pr else pr_url
    commit_url = (lambda sha: f'{pr_url}/commits/{sha}') if has_pr else (lambda sha: f'{repo_url}/commit/{sha}')

    def file_links(p):
        d = f'{files_url}#diff-{hashlib.sha256(p.encode()).hexdigest()}'
        return {'diff': d, 'diffLineNew': d + 'R{a}', 'diffLineOld': d + 'L{a}',
                'diffRangeNew': d + 'R{a}-R{b}', 'diffRangeOld': d + 'L{a}-L{b}',
                'blobHeadRange': f'{repo_url}/blob/{head_sha}/{p}#L{{a}}-L{{b}}',
                'blobBaseRange': f'{repo_url}/blob/{base_sha}/{p}#L{{a}}-L{{b}}'}
elif host == 'azure':
    repo_url = azure_url
    pr_url = f'{repo_url}/pullrequest/{pr}' if has_pr else f'{repo_url}/branchCompare?baseVersion=GC{base_sha}&targetVersion=GC{head_sha}&_a=files'
    files_url = f'{pr_url}?_a=files' if has_pr else pr_url
    commits_url = f'{pr_url}?_a=commits' if has_pr else pr_url
    commit_url = lambda sha: f'{repo_url}/commit/{sha}'

    def file_at(sha, p):
        return f'{repo_url}?path=/{urllib.parse.quote(p)}&version=GC{sha}&_a=contents'

    def file_links(p):
        d = f'{files_url}&path=/{urllib.parse.quote(p)}' if has_pr else f'{pr_url}&path=/{urllib.parse.quote(p)}'
        lines = '&line={a}&lineEnd={b}&lineStartColumn=1&lineEndColumn=1&lineStyle=plain'
        return {'diff': d, 'diffLineNew': d, 'diffLineOld': d, 'diffRangeNew': d, 'diffRangeOld': d,
                'blobHeadRange': file_at(head_sha, p) + lines, 'blobBaseRange': file_at(base_sha, p) + lines}
else:
    repo_url = f'https://bitbucket.org/{slug}'
    pr_url = f'{repo_url}/pull-requests/{pr}' if has_pr else f'{repo_url}/branches/compare/{head_sha}%0D{base_sha}#diff'
    files_url = f'{pr_url}/diff' if has_pr else pr_url
    commits_url = f'{pr_url}/commits' if has_pr else pr_url
    commit_url = lambda sha: f'{repo_url}/commits/{sha}'

    def file_links(p):
        q = urllib.parse.quote(p, safe='')
        d = f'{files_url}#chg-{p}'
        return {'diff': d, 'diffLineNew': f'{files_url}#L{q}T{{a}}', 'diffLineOld': f'{files_url}#L{q}F{{a}}',
                'diffRangeNew': f'{files_url}#L{q}T{{a}}', 'diffRangeOld': f'{files_url}#L{q}F{{a}}',
                'blobHeadRange': f'{repo_url}/src/{head_sha}/{p}#lines-{{a}}:{{b}}',
                'blobBaseRange': f'{repo_url}/src/{base_sha}/{p}#lines-{{a}}:{{b}}'}

commits = []
for line in git('log', '--reverse', '--format=%H%x09%an%x09%ad%x09%s', '--date=short', f'{base_sha}..{head_sha}').splitlines():
    sha, author, date, subject = line.split('\t', 3)
    commits.append({'sha': sha, 'short': sha[:7], 'author': author, 'date': date, 'subject': subject, 'url': commit_url(sha)})

paths = set()
for src in sources:
    data = json.load(open(src, encoding='utf-8'))
    if 'topics' in data:
        for topic in data['topics'].values():
            paths.update(i['file'] for i in topic['items'])
    else:
        paths.update(p['file'] for p in data.values())

meta = {'host': host, 'repo': slug, 'repoUrl': repo_url, 'number': int(pr) if has_pr else None, 'prUrl': pr_url,
        'filesUrl': files_url, 'commitsUrl': commits_url, 'base': base_sha, 'head': head_sha,
        'fileAtHead': {'github': f'{repo_url}/blob/{head_sha}/{{path}}', 'bitbucket': f'{repo_url}/src/{head_sha}/{{path}}',
                       'azure': f'{repo_url}?path=/{{path}}&version=GC{head_sha}&_a=contents'}[host],
        'commits': commits, 'files': {p: file_links(p) for p in sorted(paths)}}
json.dump(meta, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'host={host} pr={pr_url} commits={len(commits)} files={len(meta["files"])}')
