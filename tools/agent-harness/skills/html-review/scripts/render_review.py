#!/usr/bin/env python3
"""Render a local review as offline HTML; no network or project mutation."""
import argparse
import html
import re
from pathlib import Path
from urllib.parse import quote, urlsplit
from markdown_it import MarkdownIt
from bs4 import BeautifulSoup

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--title', required=True)
parser.add_argument('--subtitle', default='')
args = parser.parse_args()
source = args.input.read_text()
# Promote standalone bold section labels often used in conversational reviews.
source = re.sub(r'^\*\*([^\n]+)\*\*\s*$', r'## \1', source, flags=re.M)
body = BeautifulSoup(MarkdownIt('commonmark').enable('table').render(source), 'html.parser')
# The HTML title is supplied separately, so do not repeat the document H1.
first = body.find('h1')
if first:
    first.decompose()
# Source excerpts must never introduce scripts, remote embeds or event handlers.
allowed = {'p','a','strong','em','code','pre','ul','ol','li','h2','h3','h4','h5','h6','blockquote','table','thead','tbody','tr','th','td','hr','br','del','details','summary'}
for tag in list(body.find_all(True)):
    if tag.parent is None:
        continue
    if tag.name in {'script','style','iframe','object','embed','form','input','button','img','link','meta','svg'}:
        tag.decompose()
        continue
    if tag.name not in allowed:
        tag.unwrap()
        continue
    for attr in list(tag.attrs):
        if attr not in {'href','id','title','colspan','rowspan','start'}:
            del tag[attr]
    if tag.name == 'a' and tag.has_attr('href'):
        href = tag['href']
        scheme = urlsplit(href).scheme.lower()
        if scheme and scheme not in {'https','http','file','mailto'}:
            del tag['href']
            continue
        if href.startswith('/'):
            match = re.match(r'^(.*):(\d+)$', href)
            if match:
                href, line = match.groups()
                tag['title'] = f'Line {line}: {href}'
                tag['data-line'] = line
            tag['href'] = Path(href).as_uri()
        elif scheme in {'http','https'}:
            tag['rel'] = 'noreferrer'
for table in body.find_all('table'):
    wrap = body.new_tag('div', attrs={'class':'table-wrap','tabindex':'0','role':'region','aria-label':'Scrollable table'})
    table.wrap(wrap)
    for cell in table.find_all('th'):
        cell['scope'] = 'col'
nav=[]
for i, heading in enumerate(body.find_all('h2'), 1):
    anchor=heading.get('id',f'section-{i}')
    heading['id']=anchor
    nav.append(f'<li><a href="#{html.escape(anchor, quote=True)}">{html.escape(heading.get_text())}</a></li>')
css=(Path(__file__).resolve().parents[1]/'assets/review.css').read_text()
output=f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{html.escape(args.title)}</title><style>{css}</style></head>
<body><a class="skip" href="#content">Skip to content</a><div class="layout"><aside aria-label="Document navigation"><div class="eyebrow">Review desk</div><div class="brand">Umar Ali</div><nav aria-label="Sections"><ul>{''.join(nav)}</ul></nav></aside><main id="content"><header><div class="eyebrow">Review document</div><h1>{html.escape(args.title)}</h1><p>{html.escape(args.subtitle)}</p></header><article>{body}</article><footer>Standalone HTML · No external assets · Print from your browser. Local evidence links require the original workspace.</footer></main></div></body></html>'''
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(output)
print(f'{args.output} ({len(output.encode())} bytes)')
