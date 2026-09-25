"""
Report: how well do the site crawls find articles about Dario Amodei's 'We Must Pace the Frontier'
(published 2026-09-12)? Reads data/interim/site_crawls/*/pages.jsonl and the saved HTML; writes
    tmp_report.md   per-site coverage of the week after publication, and what each way of finding
                    articles about the essay turns up (exact link, any darioamodei.com link incl. redirect-
                    wrapped ones, a mention in the title, a mention in the page itself)
    tmp.jsonl       one line per candidate article, with which of those found it

    python tmp.py        (tmp.slurm runs it on Alpine)
"""
import glob
import json
import os
import re
from collections import Counter
from urllib.parse import unquote

import pyarrow.parquet as pq

CRAWLS = 'data/interim/site_crawls'
WINDOW = ('2026-09-12', '2026-09-19')  # the essay's publication date to a week later
EXACT = 'darioamodei.com/post/we-must-pace-the-frontier'
MENTION = re.compile(r'Amodei|阿莫迪|阿莫代|达里奥|Dario', re.I)
ESSAY = re.compile(r'pace[- ]the[- ]frontier|前沿.{0,4}(节奏|步伐|速度)|(节奏|步伐|速度).{0,6}前沿', re.I)


def in_window(pubdate):
    return bool(pubdate) and WINDOW[0] <= pubdate[:10] <= WINDOW[1]


def read_pages(domain_dir):
    """Rows of a site's pages.jsonl; the count of lines that aren't JSON (a crawl still writing)."""
    pages, n_bad = [], 0
    path = os.path.join(domain_dir, 'pages.jsonl')
    if not os.path.exists(path):
        return pages, n_bad
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                pages.append(json.loads(line))
            except json.JSONDecodeError:
                n_bad += 1
    return pages, n_bad


def link_flags(links):
    decoded = [unquote(unquote(link)).lower() for link in links]  # redirect wrappers encode the target
    return {'exact_link': any(EXACT in link for link in links),
            'any_darioamodei_link': any('darioamodei.com' in link for link in decoded),
            'encoded_link_only': any(EXACT in link for link in decoded) and not any(EXACT in link for link in links)}


def scan_html(domain_dir, urls):
    """{url: (mentions Amodei in the HTML, mentions the essay, has darioamodei.com anywhere)} for the given
    urls, from the site's saved HTML Parquet files."""
    found = {}
    for path in sorted(glob.glob(os.path.join(domain_dir, 'html', '*.parquet'))):
        file_urls = pq.read_table(path, columns=['url']).column('url').to_pylist()
        wanted = [i for i, url in enumerate(file_urls) if url in urls]
        if not wanted:
            continue
        table = pq.read_table(path, columns=['url', 'html']).take(wanted)
        for url, html in zip(table.column('url').to_pylist(), table.column('html').to_pylist()):
            text = html.decode('utf-8', errors='replace')
            found[url] = (bool(MENTION.search(text)), bool(ESSAY.search(text)), 'darioamodei.com' in text)
    return found


def main():
    sites, candidates = [], []
    for domain_dir in sorted(glob.glob(os.path.join(CRAWLS, '*'))):
        domain = os.path.basename(domain_dir)
        pages, n_bad = read_pages(domain_dir)
        window_pages = [p for p in pages if in_window(p.get('pubdate'))]
        pubdates = sorted(p['pubdate'][:10] for p in pages if p.get('pubdate') and p['pubdate'][:10] <= '2026-12-31')
        html_hits = scan_html(domain_dir, {p['url'] for p in window_pages})
        site = Counter(pages=len(pages), bad_lines=n_bad, window_pages=len(window_pages),
                       html_files=len(glob.glob(os.path.join(domain_dir, 'html', '*.parquet'))),
                       window_pages_with_html=len(html_hits))
        for page in pages:
            flags = link_flags(page.get('links', []))
            window = in_window(page.get('pubdate'))
            title_mention = window and bool(MENTION.search(page.get('title') or ''))
            body_mention, body_essay, body_link = html_hits.get(page['url'], (False, False, False))
            if flags['exact_link'] or flags['any_darioamodei_link'] or title_mention or body_mention:
                row = {'domain': domain, 'url': page['url'], 'title': page.get('title'), 'pubdate': page.get('pubdate'),
                       'pubdate_source': page.get('pubdate_source'), 'in_window': window, **flags,
                       'title_mentions_amodei': title_mention, 'html_mentions_amodei': body_mention,
                       'html_mentions_essay': body_essay, 'html_has_darioamodei': body_link}
                candidates.append(row)
                for key in ('exact_link', 'any_darioamodei_link', 'encoded_link_only', 'title_mentions_amodei',
                            'html_mentions_amodei', 'html_mentions_essay', 'html_has_darioamodei'):
                    site[key] += row[key]
        sites.append((domain, site, pubdates[0] if pubdates else '', pubdates[-1] if pubdates else ''))

    with open('tmp.jsonl', 'w', encoding='utf-8') as f:
        for row in candidates:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    write_report(sites, candidates)


def write_report(sites, candidates):
    total = Counter()
    for _, site, _, _ in sites:
        total.update(site)
    lines = [f'# Finding coverage of "We Must Pace the Frontier" ({WINDOW[0]} to {WINDOW[1]})', '',
             f'{len(sites)} sites, {total["pages"]} pages crawled ({total["bad_lines"]} unreadable lines skipped), '
             f'{total["window_pages"]} with a pubdate in the '
             f'window ({total["window_pages_with_html"]} of them with saved HTML). Pages whose HTML is not in a '
             'Parquet file yet (a site writes one per 1000 pages) have no HTML checks.', '',
             '## Ways of finding articles about the essay (all pages; window pages for mentions)', '',
             f'- exact link to {EXACT}: {total["exact_link"]}',
             f'- any darioamodei.com link, redirect-wrapped ones decoded: {total["any_darioamodei_link"]} '
             f'(found only after decoding: {total["encoded_link_only"]})',
             f'- window page, Amodei in the title: {total["title_mentions_amodei"]}',
             f'- window page, Amodei anywhere in its HTML: {total["html_mentions_amodei"]}',
             f'- window page, the essay itself (pace the frontier / 前沿…节奏) in its HTML: {total["html_mentions_essay"]}',
             f'- window page, darioamodei.com anywhere in its HTML (not only links): {total["html_has_darioamodei"]}',
             '', '## Per site', '',
             '| site | pages | window pages | w/ HTML | HTML files | pubdates | exact link | any link | title '
             '| html amodei | html essay |',
             '|---|---|---|---|---|---|---|---|---|---|---|']
    for domain, s, first, last in sorted(sites, key=lambda x: -x[1]['pages']):
        lines.append(f'| {domain} | {s["pages"]} | {s["window_pages"]} | {s["window_pages_with_html"]} | '
                     f'{s["html_files"]} | {first} – {last} | {s["exact_link"]} | {s["any_darioamodei_link"]} | '
                     f'{s["title_mentions_amodei"]} | {s["html_mentions_amodei"]} | {s["html_mentions_essay"]} |')
    about_essay = [c for c in candidates if c['html_mentions_essay'] or c['exact_link'] or c['any_darioamodei_link']]
    lines += ['', f'## Pages that link to or discuss the essay ({len(about_essay)})', '']
    for c in sorted(about_essay, key=lambda c: (c['pubdate'] or '', c['domain'])):
        how = ', '.join(k for k in ('exact_link', 'any_darioamodei_link', 'html_mentions_essay') if c[k])
        lines.append(f'- {c["pubdate"]} {c["domain"]} [{how}] {c["title"]} {c["url"]}')
    with open('tmp_report.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:14]))
    print(f'\n-> tmp_report.md, tmp.jsonl ({len(candidates)} candidate pages)')


if __name__ == '__main__':
    main()
