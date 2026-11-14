"""Assembles the self-contained walkthrough page.

Replaces every /*__NAME__*/{} (or [], or "") placeholder in the page template with the file given as NAME=path
(CODE = code_panels.py output, TOPICS = pr_topics.py output, HUMAN = topic sentences, LANES = the code tour, ...).
A .json file goes in as it is; any other file (TONE = pr-review's ton-komentara.md) goes in as a JSON string.
A placeholder without a file keeps its default.

Usage: python -I build_page.py <page-template.html> <out.html> [CODE=code-panels.json] [TOPICS=topics.json] ...
"""
import json
import pathlib
import re
import sys

template, out, *data_args = sys.argv[1:]
html = pathlib.Path(template).read_text(encoding='utf-8')

for arg in data_args:
    name, path = arg.split('=', 1)
    source = pathlib.Path(path)
    text = source.read_text(encoding='utf-8')
    data = (text if source.suffix.lower() == '.json' else json.dumps(text, ensure_ascii=False)).replace('</', '<\\/')
    html, n = re.subn(r'/\*__%s__\*/(\{\}|\[\]|"")?' % name, lambda _: data, html)
    print(f'{name}: {n} placeholder(s)')

pathlib.Path(out).write_text(html, encoding='utf-8', newline='\n')
print(f'size={pathlib.Path(out).stat().st_size // 1024}KB')
