"""Makes a PR's page template from the shared reference template: only the PR-specific blocks change.

The reference (reference-template.html) carries all CSS, JS and behaviour; its PR-specific parts sit between markers
<!--@NAME--> … <!--/@NAME-->: HEADER (h1 and lead), EKRANI (the Ekrani tab, written by verify_screens.py; empty hides
the tab), IZA (extra content under the code tour, e.g. a diagram; empty is fine), FOOTER (Na što paziti, Pojmovnik,
Otvorena pitanja). <parts_dir> holds title.txt, header.html, ekrani.html, iza.html and footer.html; a missing file empties
that block.

Every page also gets the IDE layer from ide/ (title bar, file tree, status bar): ide.css as a second
<style id="ide-layer"> right after the main <style>, ide.js as <script id="ide-shell"> after the main script. ide.js reads
the page's PRINFO, META, SRC.files, CODE, OUTLINE, view, drawer, WIDE, renderView and openCommentTarget; renaming any of
them in reference-template.html breaks it.

The page also carries ask_server.py as plain text (<script type="text/plain" id="ask-helper-src">), so a viewer can download
the "Pitaj Claude" helper from the page itself.

Usage: python -I make_page.py <reference-template.html> <parts_dir> <out page-template.html>
"""
import pathlib
import re
import sys

TOOLS_DIR = pathlib.Path(__file__).parent
PART_FILES = {'HEADER': 'header.html', 'EKRANI': 'ekrani.html', 'IZA': 'iza.html', 'FOOTER': 'footer.html'}

ref, parts, out = map(pathlib.Path, sys.argv[1:4])
html = ref.read_text(encoding='utf-8')
ide_css = (TOOLS_DIR / 'ide' / 'ide.css').read_text(encoding='utf-8').strip()
ide_js = (TOOLS_DIR / 'ide' / 'ide.js').read_text(encoding='utf-8').strip()
html = html.replace('</style>', '</style>\n<style id="ide-layer">\n' + ide_css + '\n</style>', 1)
head, sep, tail = html.rpartition('</body>')
helper = (TOOLS_DIR / 'ask_server.py').read_text(encoding='utf-8')
if '</script' in helper.lower() or '<!--' in helper:
    raise SystemExit('ask_server.py must not contain </script or <!-- (it is embedded in a <script> block)')
html = (head + '<script id="ide-shell">\n' + ide_js + '\n</script>\n'
        + '<script type="text/plain" id="ask-helper-src">\n' + helper + '</script>\n' + sep + tail)
title = parts / 'title.txt'
if title.exists():  # <title> can't hold comment markers (they'd show as text), so it is replaced whole
    html = re.sub(r'<title>.*?</title>', lambda _: f'<title>{title.read_text(encoding="utf-8").strip()}</title>', html, count=1, flags=re.S)
for name, file in PART_FILES.items():
    p = parts / file
    content = p.read_text(encoding='utf-8').strip() if p.exists() else ''
    html, n = re.subn(r'(<!--@%s-->).*?(<!--/@%s-->)' % (name, name), lambda m: m.group(1) + '\n' + content + '\n' + m.group(2),
                      html, count=1, flags=re.S)
    if n != 1:
        raise SystemExit(f'marker {name} missing in {ref}')
out.write_text(html, encoding='utf-8', newline='\n')
print(f'{out} ({", ".join(f"{k}={"yes" if (parts / v).exists() else "empty"}" for k, v in PART_FILES.items())})')
