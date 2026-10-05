#!/usr/bin/env python
"""
A local page for reviewing the English screenshots found in the Chinese crawls, six at a time: click the ones to
keep, then Next (or Enter); the others are discarded. Decisions go to a YAML file as you go
(src/screenshot_review.py), so stop any time and run it again to carry on where you left off. Images load straight
from their sites (no Referer, which most Chinese image hosts accept); an image that refuses is fetched through this
server with its article as Referer instead, in memory, never saved.

Run as a module from the repo root, then open http://localhost:8765:
    python -m scripts.review_screenshots -tsv /tmp/english_screenshot_links.tsv
    python -m scripts.review_screenshots -tsv /tmp/english_screenshot_links.tsv -notable-only
"""
import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import httpx

from src.screenshot_review import load_decisions, load_screenshots, next_batch, record, save_decisions

PAGE = '''<!doctype html><html><head><meta charset="utf-8"><title>Screenshot review</title><style>
:root { --bg: #f4f5f7; --card: #fff; --ink: #1b1f24; --muted: #66707a; --keep: #1f7a3d; --line: #d9dde1 }
@media (prefers-color-scheme: dark) { :root { --bg: #111417; --card: #1a1f24; --ink: #e5e9ec; --muted: #94a0a8;
  --keep: #5fd08a; --line: #2c343b } }
body { margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.4 -apple-system, "Segoe UI", sans-serif }
header { display: flex; gap: 16px; align-items: center; padding: 12px 20px; position: sticky; top: 0;
  background: var(--bg); border-bottom: 1px solid var(--line); z-index: 1 }
header b { font-size: 16px } .muted { color: var(--muted) }
button { font: 600 14px inherit; padding: 8px 18px; border-radius: 6px; border: 0; background: var(--keep);
  color: #fff; cursor: pointer }
.grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; padding: 16px 20px }
@media (max-width: 900px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)) } }
.card { background: var(--card); border: 3px solid var(--line); border-radius: 8px; overflow: hidden;
  cursor: pointer; display: flex; flex-direction: column }
.card.keep { border-color: var(--keep) } .card.keep .tag { display: inline-block }
.card img { width: 100%; height: 340px; object-fit: contain; background: #000 }
.meta { padding: 8px 10px; display: grid; gap: 3px; font-size: 12px }
.tag { display: none; background: var(--keep); color: #fff; border-radius: 3px; padding: 0 6px; font-weight: 600 }
.ocr { color: var(--muted); max-height: 3.9em; overflow: hidden } a { color: inherit }
</style></head><body><header><b>Screenshot review</b><span class="muted" id="count"></span>
<span class="muted">click to keep &middot; Enter or Next to save (the rest are discarded)</span>
<button id="next">Next</button></header><div class="grid" id="grid"></div><script>
let batch = [];
const esc = s => String(s || '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
async function load() {
  const r = await (await fetch('/batch')).json();
  batch = r.rows;
  document.getElementById('count').textContent = `${r.done} reviewed, ${r.kept} kept, ${r.left} left`;
  document.getElementById('grid').innerHTML = batch.map((row, i) => `<div class="card" data-i="${i}">
    <img src="${esc(row.src)}" referrerpolicy="no-referrer" loading="eager"
         onerror="if (!this.dataset.proxied) { this.dataset.proxied = 1;
                  this.src = '/img?src=' + encodeURIComponent(${esc(JSON.stringify(row.src))}) +
                             '&page=' + encodeURIComponent(${esc(JSON.stringify(row.page))}); }">
    <div class="meta"><div><span class="tag">keep</span> <b>${esc(row.kind)}</b> &middot; ${esc(row.site)}
      &middot; ${esc(row.date || 'no date')}</div>
    <div>${esc(row.accounts) || '<span class="muted">no notable account</span>'}</div>
    <div class="ocr">${esc(row.ocr)}</div>
    <div><a href="${esc(row.page)}" target="_blank" onclick="event.stopPropagation()">article</a> &middot;
         <a href="${esc(row.src)}" target="_blank" onclick="event.stopPropagation()">image</a></div></div></div>`)
    .join('')
    || '<p>All reviewed.</p>';
  document.querySelectorAll('.card').forEach(c => c.onclick = () => c.classList.toggle('keep'));
  window.scrollTo(0, 0);
}
async function next() {
  if (!batch.length) return;
  const keep = [...document.querySelectorAll('.card.keep')].map(c => batch[c.dataset.i].src);
  await fetch('/decide', {method: 'POST', body: JSON.stringify({srcs: batch.map(r => r.src), keep})});
  load();
}
document.getElementById('next').onclick = next;
document.addEventListener('keydown', e => { if (e.key === 'Enter') next(); });
load();
</script></body></html>'''


def parse_args():
    parser = argparse.ArgumentParser(description='Review English screenshots six at a time')
    parser.add_argument('-tsv', required=True, help='scripts/export_english_screenshots.py output')
    parser.add_argument('-out', default='data/processed/screenshot_reviews.yml', help='decisions (YAML)')
    parser.add_argument('-notable-only', action='store_true')
    parser.add_argument('-port', type=int, default=8765)
    return parser.parse_args()


def make_handler(rows, decisions, out, lock):
    by_src = {r['src']: r for r in rows}
    client = httpx.Client(headers={'User-Agent': 'Mozilla/5.0'}, follow_redirects=True, timeout=20)

    class Handler(BaseHTTPRequestHandler):
        def send(self, body, content_type):
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == '/':
                self.send(PAGE.encode(), 'text/html; charset=utf-8')
            elif url.path == '/batch':
                done = sum(r['src'] in decisions for r in rows)
                kept = sum(d['decision'] == 'keep' for d in decisions.values())
                self.send(json.dumps({'rows': next_batch(rows, decisions), 'done': done, 'kept': kept,
                                      'left': len(rows) - done}).encode(), 'application/json')
            elif url.path == '/img':
                q = parse_qs(url.query)
                try:
                    r = client.get(q['src'][0], headers={'Referer': q['page'][0]})
                    self.send(r.content, r.headers.get('content-type', 'image/jpeg'))
                except Exception:
                    self.send_error(502)
            else:
                self.send_error(404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with lock:
                for src in body['srcs']:
                    if src in by_src:
                        record(decisions, by_src[src], 'keep' if src in body['keep'] else 'discard')
                save_decisions(out, decisions)
            self.send(b'{}', 'application/json')

        def log_message(self, *args):
            pass

    return Handler


def main():
    args = parse_args()
    rows = load_screenshots(args.tsv, args.notable_only)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    decisions = load_decisions(args.out)
    print(f'{len(rows)} screenshots, {sum(r["src"] in decisions for r in rows)} already reviewed -> {args.out}')
    print(f'open http://localhost:{args.port}  (Ctrl-C to stop; run again to resume)')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(rows, decisions, args.out, threading.Lock()))
    server.serve_forever()


if __name__ == '__main__':
    main()
