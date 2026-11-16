"""Turns a verify-app result into the Ekrani tab of a walkthrough page.

Reads verify.json and its images from verify-app's output folder and writes the EKRANI part (parts/ekrani.html): one block
per scenario, "Prije" and "Poslije" side by side where verify-app took a pair, marks as numbered boxes, and the images
embedded as data URIs so the page stays one file. A mark whose file is a code panel opens that panel; the marked files are
also listed under the block, which links the screenshots to the code in the "Na ekranu" panel. When the PR's files differ
between the commit the screenshots were taken on and the page's head, the tab says the screens may be out of date (a merge
commit of the same PR does not count as different).

Usage: python -I verify_screens.py <verify dir> <code-panels.json> <repo> <base sha> <head sha> <out ekrani.html>
"""
import base64
import html
import json
import pathlib
import subprocess
import sys

IMAGE_TYPES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
VERDICT_LABELS = {'pass': 'prošlo', 'fail': 'palo', 'partial': 'djelomično provjereno', 'blocked': 'nije se moglo provjeriti'}
SIDE_LABELS = {'before': ('b', 'Prije'), 'after': ('a', 'Poslije')}

verify_dir, panels_path, repo, base, head, out = sys.argv[1:7]
verify_dir = pathlib.Path(verify_dir)
result = json.loads((verify_dir / 'verify.json').read_text(encoding='utf-8-sig'))
panels = json.loads(pathlib.Path(panels_path).read_text(encoding='utf-8')) if pathlib.Path(panels_path).exists() else {}
panel_by_file = {}
for key, panel in panels.items():
    if panel.get('side') != 'base':
        panel_by_file.setdefault(panel.get('file'), key)


def git(*args):
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, encoding='utf-8')


def pr_files_changed_since(screens_commit):
    if not screens_commit or screens_commit == head:
        return False
    pr_files = git('diff', '--name-only', base, head).stdout.split()
    since = git('diff', '--name-only', screens_commit, head, '--', *pr_files)
    return since.returncode != 0 or bool(since.stdout.strip())


def text(value):
    return html.escape(str(value or ''), quote=True)


def data_uri(relative_path):
    image = verify_dir / relative_path
    mime = IMAGE_TYPES.get(image.suffix.lower())
    if not mime or not image.is_file():
        raise SystemExit(f'image missing or not an image: {image}')
    return f'data:{mime};base64,' + base64.b64encode(image.read_bytes()).decode('ascii')


def mark_html(mark):
    code_key = panel_by_file.get(mark.get('file'))
    link = f' data-code="{text(code_key)}"' if code_key else ''
    box = f'left:{mark["x"]}%;top:{mark["y"]}%;width:{mark["w"]}%;height:{mark["h"]}%'
    return f'<div class="mark"{link} style="{box}"><b>{text(mark["n"])}</b></div>'


def shot_html(shot):
    marks = ''.join(mark_html(m) for m in shot.get('marks', []))
    alt = text(shot.get('caption') or shot['file'])
    return f'<div class="shot" onclick="zoom(this)"><img src="{data_uri(shot["file"])}" alt="{alt}">{marks}</div>'


def legend_html(shots):
    items = [m for shot in shots for m in shot.get('marks', []) if m.get('label')]
    if not items:
        return ''
    rows = ''.join(f'<li><span>{text(m["n"])}</span><span>{text(m["label"])}</span></li>' for m in items)
    return f'<ul class="legend">{rows}</ul>'


def files_html(shots):
    files = list(dict.fromkeys(m['file'] for shot in shots for m in shot.get('marks', []) if m.get('file')))
    if not files:
        return ''
    return '<div class="incode">u kodu: ' + ', '.join(f'<code>{text(f)}</code>' for f in files) + '</div>'


def checks_html(checks):
    rows = []
    for check in checks:
        outcome = check.get('status', check.get('exitCode', ''))
        what = check.get('request') or check.get('command') or check.get('kind')
        rows.append(f'<div class="incode">{text(check.get("kind"))} ({text(SIDE_LABELS.get(check.get("side"), ("", ""))[1].lower())}): '
                    f'<code>{text(what)}</code> → {text(outcome)}{" · " + text(check["log"]) if check.get("log") else ""}</div>')
    return ''.join(rows)


def scenario_intro(scenario):
    verdict = VERDICT_LABELS.get(scenario.get('verdict'), scenario.get('verdict'))
    return (f'<p><strong>{text(verdict).capitalize()}.</strong><br>Očekivano: {text(scenario.get("expected"))}<br>'
            f'Dobiveno: {text(scenario.get("actual"))}</p>')


def compare_html(scenario, before, after, title):
    columns = ''
    for shot in (before, after):
        css, label = SIDE_LABELS[shot['side']]
        columns += (f'<div><div class="side-label {css}">{label}</div>{shot_html(shot)}'
                    f'<div class="cap">{text(shot.get("caption"))}</div></div>')
    return (f'<div class="compare"><h3>{text(title)}</h3>{scenario_intro(scenario)}<div class="cols">{columns}</div>'
            f'{legend_html([after])}{files_html([before, after])}</div>')


def step_html(scenario, shot, title, number):
    return (f'<div class="step">{shot_html(shot)}<div><h3><span class="step-num">{number}</span>{text(title)}</h3>'
            f'{scenario_intro(scenario)}<p>{text(shot.get("caption"))}</p>{legend_html([shot])}{files_html([shot])}</div></div>')


def scenario_html(scenario, step_numbers):
    shots = scenario.get('shots', [])
    befores = [s for s in shots if s.get('side') == 'before']
    afters = [s for s in shots if s.get('side') != 'before']
    blocks = []
    for i, after in enumerate(afters):
        title = scenario['title'] if i == 0 else f'{scenario["title"]} ({i + 1})'
        if i < len(befores):
            blocks.append(compare_html(scenario, befores[i], after, title))
        else:
            blocks.append(step_html(scenario, after, title, next(step_numbers)))
    for before in befores[len(afters):]:
        blocks.append(step_html(scenario, before, f'{scenario["title"]} (prije)', next(step_numbers)))
    if not shots:
        blocks.append(f'<div class="step"><div></div><div><h3><span class="step-num">{next(step_numbers)}</span>{text(scenario["title"])}</h3>'
                      f'{scenario_intro(scenario)}{checks_html(scenario.get("checks", []))}</div></div>')
    elif scenario.get('checks'):
        blocks.append(checks_html(scenario['checks']))
    return '\n'.join(blocks)


def counter():
    n = 0
    while True:
        n += 1
        yield n


verify_head = (result.get('target') or {}).get('head') or ''
app = result.get('app') or {}
intro = f'Aplikacija {text(app.get("name"))} pokrenuta lokalno; ishod: <strong>{text(VERDICT_LABELS.get(result.get("verdict"), result.get("verdict")))}</strong>.'
if pr_files_changed_since(verify_head):
    intro += f' Slike su s commita <code>{text(verify_head[:7])}</code>, a PR je sad na <code>{text(head[:7])}</code>: ekrani možda više nisu takvi.'
parts = ['<h2>Kako izgleda u aplikaciji</h2>', f'<p class="section-intro">{intro} Klik na sliku je poveća.</p>']
numbers = counter()
parts += [scenario_html(s, numbers) for s in result.get('scenarios', [])]
if result.get('notCovered'):
    parts.append('<h2>Što nije provjereno u aplikaciji</h2><ul>' + ''.join(f'<li>{text(n)}</li>' for n in result['notCovered']) + '</ul>')

out_path = pathlib.Path(out)
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text('\n'.join(parts) + '\n', encoding='utf-8', newline='\n')
shots = sum(len(s.get('shots', [])) for s in result.get('scenarios', []))
linked = sum(1 for s in result.get('scenarios', []) for shot in s.get('shots', []) for m in shot.get('marks', []) if panel_by_file.get(m.get('file')))
print(f'{out_path} (scenarios={len(result.get("scenarios", []))}, shots={shots}, marks linked to code={linked})')
