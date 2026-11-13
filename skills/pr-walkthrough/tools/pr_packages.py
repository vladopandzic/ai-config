"""Adds, to every package in topics.json, where the code uses it and how healthy the package version is.

- usage: the files that import the package (`using X` / `@using X` by default, or the overrides' `pattern`), at the PR's
  head, grouped by project, with the project the PR added it to marked.
- health, from the public NuGet API (only package ids and versions are sent): newest stable version, licence, published
  date, deprecation, and known vulnerabilities of THIS version.

topics-human.json can override, per package item: "namespace" (when it differs from the package id, e.g.
Microsoft.Extensions.TimeProvider.Testing → Microsoft.Extensions.Time.Testing) or a full git-grep "pattern".

Usage: python -I pr_packages.py <repo> <head> <topics.json> [topics-human.json]
"""
import gzip
import json
import re
import subprocess
import sys
import urllib.request

repo, head, topics_path, *rest = sys.argv[1:]
human = json.load(open(rest[0], encoding='utf-8')) if rest else {}
data = json.load(open(topics_path, encoding='utf-8'))


def get_json(url):
    request = urllib.request.Request(url, headers={'Accept-Encoding': 'gzip', 'User-Agent': 'pr-walkthrough'})
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read()
        if response.headers.get('Content-Encoding') == 'gzip' or body[:2] == b'\x1f\x8b':
            body = gzip.decompress(body)
        return json.loads(body)


def version_key(v):
    return [int(x) if x.isdigit() else x for x in re.split(r'[.+-]', v)]


def health(package, version):
    pid = package.lower()
    try:
        versions = get_json(f'https://api.nuget.org/v3-flatcontainer/{pid}/index.json')['versions']
        stable = [v for v in versions if '-' not in v]
        latest = max(stable, key=version_key) if stable else versions[-1]
        # A newer MAJOR often means a newer .NET (10.x for net10), so also say what's newest on the same major line.
        same_major = [v for v in stable if v.split('.')[0] == version.split('.')[0]]
        latest_same_major = max(same_major, key=version_key) if same_major else version
        leaf = get_json(f'https://api.nuget.org/v3/registration5-gz-semver2/{pid}/{version.lower()}.json')
        entry = get_json(leaf['catalogEntry']) if isinstance(leaf.get('catalogEntry'), str) else leaf.get('catalogEntry', {})
    except Exception as ex:  # offline, private feed, or unknown version: say so instead of guessing
        return {'error': f'NuGet nije odgovorio ({type(ex).__name__})'}
    deprecation = entry.get('deprecation')
    return {
        'latest': latest,
        'isLatest': version_key(version) >= version_key(latest),
        'latestSameMajor': latest_same_major,
        'isLatestSameMajor': version_key(version) >= version_key(latest_same_major),
        'license': entry.get('licenseExpression') or ('vidi licencu' if entry.get('licenseUrl') else 'nepoznata'),
        'licenseUrl': entry.get('licenseUrl') or f'https://www.nuget.org/packages/{package}/{version}#licenseexpression',
        'published': (entry.get('published') or '')[:10],
        'deprecated': bool(deprecation),
        'deprecationReason': ', '.join(deprecation.get('reasons', [])) if deprecation else '',
        'vulnerabilities': [{'severity': v.get('severity'), 'url': v.get('advisoryUrl')} for v in entry.get('vulnerabilities') or []],
        'nugetUrl': f'https://www.nuget.org/packages/{package}/{version}',
    }


def override(item):
    for h in human.get('items', []):
        if h.get('topic') == 'packages' and (item['id'].startswith(h['match']) or item['text'].startswith(h['match'])):
            return h
    return {}


def usage(item):
    o = override(item)
    pattern = o.get('pattern') or r'^\s*@?using\s+%s(\.|;|\s|$)' % re.escape(o.get('namespace') or item['package'])
    out = subprocess.run(['git', '-C', repo, 'grep', '-l', '-E', pattern, head, '--', '*.cs', '*.razor', '*.cshtml'],
                         capture_output=True).stdout.decode('utf-8', 'replace')
    files = sorted(line.split(':', 1)[1] for line in out.splitlines() if ':' in line)
    by_project = {}
    for f in files:
        by_project.setdefault(f.split('/', 1)[0], []).append(f)
    return {'count': len(files), 'projects': [{'project': p, 'files': fs, 'addedHere': p == item['project']}
                                              for p, fs in sorted(by_project.items(), key=lambda kv: kv[0] != item['project'])]}


for item in data['topics']['packages']['items']:
    if item.get('kind') == 'removed':
        item['usage'] = usage(item)
        continue
    item['usage'] = usage(item)
    item['health'] = health(item['package'], item['version'])
    h = item['health']
    print(f"{item['package']:45} {item['kind']:8} uses={item['usage']['count']:3} "
          f"latest={h.get('latest')} sameMajor={h.get('latestSameMajor')} lic={h.get('license')} vulns={len(h.get('vulnerabilities', []))} {h.get('error', '')}")

json.dump(data, open(topics_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
