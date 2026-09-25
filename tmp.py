"""
Report: how well do the site crawls find articles about Dario Amodei's 'We Must Pace the Frontier'
(published 2026-09-12)? Reads data/interim/site_crawls/*/pages.jsonl (streamed, line by line) and the saved
HTML; writes
    tmp_report.md   per-site coverage of the week after publication; what each way of finding articles about
                    the essay turns up; and every window page that mentions Amodei, with a snippet, to eyeball
    tmp.jsonl       one line per candidate page, with which checks found it

Most Chinese coverage doesn't link the essay; it paraphrases it, e.g. 21jingji: 达里奥·阿莫迪（Dario Amodei）
发文呼吁"放慢模型能力提升步伐". So a page counts as discussing the essay when it mentions Amodei and any of
the essay's themes (pace, slow down, frontier, RSI, embedded evaluators, ...).

    python tmp.py        (tmp.slurm runs it on Alpine)
"""
import glob
import json
import os
import re
import time
from collections import Counter
from urllib.parse import unquote

import pyarrow.parquet as pq

CRAWLS = 'data/interim/site_crawls'
WINDOW = ('2026-09-12', '2026-09-19')  # the essay's publication date to a week later
EXACT = 'darioamodei.com/post/we-must-pace-the-frontier'
AMODEI = re.compile(r'Amodei|阿莫迪|阿莫代|达里奥|Dario', re.I)
THEMES = re.compile(r'pace|frontier|放慢|步伐|节奏|前沿|长文|发文|递归自我改进|自我改进|RSI|嵌入式|评估员|暂停|减速', re.I)
TAGS = re.compile(r'<script\b.*?</script>|<style\b.*?</style>|<[^>]+>', re.S | re.I)
FLAGS = ('exact_link', 'any_darioamodei_link', 'encoded_link_only', 'title_mentions_amodei',
         'html_mentions_amodei', 'html_discusses_essay', 'html_has_darioamodei')


def in_window(pubdate):
    return bool(pubdate) and WINDOW[0] <= pubdate[:10] <= WINDOW[1]


def link_flags(links):
    decoded = [unquote(unquote(link)).lower() for link in links]  # redirect wrappers encode the target
    exact = any(EXACT in link for link in links)
    return {'exact_link': exact, 'any_darioamodei_link': any('darioamodei.com' in link for link in decoded),
            'encoded_link_only': not exact and any(EXACT in link for link in decoded)}


def scan_pages(path):
    """Stream a pages.jsonl. Returns counts, the pages worth keeping (in the window, or linking to
    darioamodei.com) as small dicts without their link lists, and the first and last pubdate."""
    counts, kept = Counter(), {}
    first = last = ''
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                page = json.loads(line)
            except json.JSONDecodeError:  # a line a crawl is still writing
                counts['bad_lines'] += 1
                continue
            counts['pages'] += 1
            pubdate = (page.get('pubdate') or '')[:10]
            if pubdate and pubdate <= '2026-12-31':  # htmldate sometimes guesses future dates
                first, last = min(first or pubdate, pubdate), max(last, pubdate)
            window = in_window(pubdate)
            flags = link_flags(page.get('links') or [])
            if window or flags['any_darioamodei_link']:
                counts['window_pages'] += window
                kept[page['url']] = {'url': page['url'], 'title': page.get('title'), 'pubdate': page.get('pubdate'),
                                     'pubdate_source': page.get('pubdate_source'), 'in_window': window, **flags,
                                     'title_mentions_amodei': window and bool(AMODEI.search(page.get('title') or ''))}
    return counts, kept, first, last


def scan_html(domain_dir, pages):
    """Add HTML checks to the kept pages that have saved HTML. Reads one Parquet file at a time, and only
    for the rows it needs. Returns the number of pages checked."""
    n_checked = 0
    for path in sorted(glob.glob(os.path.join(domain_dir, 'html', '*.parquet'))):
        urls = pq.read_table(path, columns=['url']).column('url').to_pylist()
        wanted = [i for i, url in enumerate(urls) if url in pages]
        if not wanted:
            continue
        table = pq.read_table(path, columns=['url', 'html']).take(wanted)
        for url, html in zip(table.column('url').to_pylist(), table.column('html').to_pylist()):
            raw = html.decode('utf-8', errors='replace')
            text = ' '.join(TAGS.sub(' ', raw).split())
            mention = AMODEI.search(text)
            page = pages[url]
            page['html_mentions_amodei'] = bool(mention)
            page['html_discusses_essay'] = bool(mention) and bool(THEMES.search(text))
            page['html_has_darioamodei'] = 'darioamodei.com' in raw
            page['snippet'] = text[max(0, mention.start() - 60):mention.end() + 120] if mention else ''
            n_checked += 1
        del table
    return n_checked


def main():
    sites, candidates = [], []
    domain_dirs = sorted(glob.glob(os.path.join(CRAWLS, '*')))
    started = time.time()
    for n, domain_dir in enumerate(domain_dirs, 1):
        domain = os.path.basename(domain_dir)
        path = os.path.join(domain_dir, 'pages.jsonl')
        print(f'[{time.time() - started:6.0f}s] site {n}/{len(domain_dirs)} {domain}: reading pages.jsonl', flush=True)
        counts, pages, first, last = scan_pages(path) if os.path.exists(path) else (Counter(), {}, '', '')
        print(f'[{time.time() - started:6.0f}s]   {counts["pages"]} pages, {counts["window_pages"]} in the window; '
              'scanning their HTML', flush=True)
        counts['window_pages_with_html'] = scan_html(domain_dir, pages)
        counts['html_files'] = len(glob.glob(os.path.join(domain_dir, 'html', '*.parquet')))
        for page in pages.values():
            page['domain'] = domain
            if any(page.get(flag) for flag in FLAGS):
                candidates.append(page)
                counts.update({flag: 1 for flag in FLAGS if page.get(flag)})
        sites.append((domain, counts, first, last))
        print(f'[{time.time() - started:6.0f}s]   done: {counts["exact_link"]} exact links, '
              f'{counts["html_mentions_amodei"]} window pages mention Amodei, '
              f'{counts["html_discusses_essay"]} discuss the essay', flush=True)
    with open('tmp.jsonl', 'w', encoding='utf-8') as f:
        for row in candidates:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    write_report(sites, candidates)


def write_report(sites, candidates):
    total = Counter()
    for _, counts, _, _ in sites:
        total.update(counts)
    lines = [f'# Finding coverage of "We Must Pace the Frontier" ({WINDOW[0]} to {WINDOW[1]})', '',
             f'{len(sites)} sites, {total["pages"]} pages crawled ({total["bad_lines"]} unreadable lines skipped), '
             f'{total["window_pages"]} with a pubdate in the window, {total["window_pages_with_html"]} of them with '
             'saved HTML. (A site saves HTML 1000 pages at a time, so its newest pages have no HTML checks yet.)', '',
             '## Ways of finding articles about the essay', '',
             f'- exact link to {EXACT}: {total["exact_link"]}',
             f'- any darioamodei.com link, redirect-wrapped ones decoded: {total["any_darioamodei_link"]} '
             f'(found only after decoding: {total["encoded_link_only"]})',
             f'- window page, Amodei in the title: {total["title_mentions_amodei"]}',
             f'- window page, Amodei in the page text: {total["html_mentions_amodei"]}',
             f'- window page, Amodei and one of the essay\'s themes in the page text: {total["html_discusses_essay"]}',
             f'- window page, darioamodei.com anywhere in the HTML: {total["html_has_darioamodei"]}',
             '', '## Per site', '',
             '| site | pages | window pages | w/ HTML | HTML files | pubdates | exact link | any link | title '
             '| text: Amodei | text: essay |',
             '|---|---|---|---|---|---|---|---|---|---|---|']
    for domain, s, first, last in sorted(sites, key=lambda x: -x[1]['pages']):
        lines.append(f'| {domain} | {s["pages"]} | {s["window_pages"]} | {s["window_pages_with_html"]} | '
                     f'{s["html_files"]} | {first} – {last} | {s["exact_link"]} | {s["any_darioamodei_link"]} | '
                     f'{s["title_mentions_amodei"]} | {s["html_mentions_amodei"]} | {s["html_discusses_essay"]} |')
    mentions = sorted((c for c in candidates if c.get('html_mentions_amodei') or c.get('any_darioamodei_link')
                       or c.get('title_mentions_amodei')), key=lambda c: (c['pubdate'] or '', c['domain']))
    lines += ['', f'## Pages that link to the essay or mention Amodei ({len(mentions)})', '']
    for c in mentions:
        how = ', '.join(flag for flag in FLAGS if c.get(flag))
        lines.append(f'- {(c["pubdate"] or "")[:10]} {c["domain"]} [{how}] {c["title"]}\n  {c["url"]}\n'
                     f'  > {c.get("snippet", "")}')
    with open('tmp_report.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:14]))
    print(f'\n-> tmp_report.md, tmp.jsonl ({len(candidates)} candidate pages)')


if __name__ == '__main__':
    main()
