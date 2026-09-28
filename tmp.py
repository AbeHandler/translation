"""
Report: how well do the site crawls find Chinese coverage of some English source posts (TARGETS)? Reads
data/interim/site_crawls/*/pages.jsonl (streamed, line by line) and the saved HTML; writes
    tmp_report.md   for each target: per-site coverage of the week after it was published; what each way of
                    finding coverage turns up; and every window page that mentions it, with a snippet to eyeball
    tmp.jsonl       one line per (target, candidate page), with which checks found it

Checks, per target:
    exact_link          a link containing the post's URL
    encoded_link_only   the post's slug only after URL-decoding (a redirect wrapper like link.zhihu.com/?target=)
    title_mentions      a window page whose title names the target's subject (e.g. Amodei)
    html_mentions       a window page whose text names it
    html_discusses      ...and also one of the post's themes. Most Chinese coverage paraphrases rather than links,
                        e.g. 21jingji: 达里奥·阿莫迪（Dario Amodei）发文呼吁"放慢模型能力提升步伐"

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
TARGETS = [
    {'name': 'pace_frontier',
     'url': 'darioamodei.com/post/we-must-pace-the-frontier',
     'slug': 'we-must-pace-the-frontier',
     'window': ('2026-09-12', '2026-09-19'),
     'mention': re.compile(r'Amodei|阿莫迪|阿莫代|达里奥|Dario', re.I),
     'themes': re.compile(r'pace|frontier|放慢|步伐|节奏|前沿|长文|发文|递归自我改进|自我改进|RSI|嵌入式|评估员|暂停|减速',
                          re.I)},
    {'name': 'distillation_attacks',
     'url': 'anthropic.com/news/detecting-and-preventing-distillation-attacks',
     'slug': 'detecting-and-preventing-distillation-attacks',
     'window': ('2026-02-23', '2026-03-02'),
     'mention': re.compile(r'Anthropic|Claude|克劳德', re.I),
     'themes': re.compile(r'distill|蒸馏|DeepSeek|深度求索|Moonshot|月之暗面|Kimi|MiniMax|稀宇|欺诈|虚假账户|'
                          r'2\.4万|24,?000|1600万|16 million', re.I)},
]
TAGS = re.compile(r'<script\b.*?</script>|<style\b.*?</style>|<[^>]+>', re.S | re.I)
FLAGS = ('exact_link', 'encoded_link_only', 'title_mentions', 'html_mentions', 'html_discusses')


def in_window(pubdate, window):
    return bool(pubdate) and window[0] <= pubdate[:10] <= window[1]


def link_flags(links, target):
    exact = any(target['url'] in link for link in links)
    decoded = any(target['slug'] in unquote(unquote(link)) for link in links)  # redirect wrappers encode it
    return {'exact_link': exact, 'encoded_link_only': decoded and not exact}


def scan_pages(path):
    """Stream a pages.jsonl. Returns per-target counts, the (target, url) pages worth keeping (in the target's
    window, or linking to it) as small dicts without their link lists, and the first and last pubdate."""
    counts = {t['name']: Counter() for t in TARGETS}
    kept = {}
    first = last = ''
    n_pages = n_bad = 0
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                page = json.loads(line)
            except json.JSONDecodeError:  # a line a crawl is still writing
                n_bad += 1
                continue
            n_pages += 1
            pubdate = (page.get('pubdate') or '')[:10]
            if pubdate and pubdate <= '2026-12-31':  # htmldate sometimes guesses future dates
                first, last = min(first or pubdate, pubdate), max(last, pubdate)
            for target in TARGETS:
                window = in_window(pubdate, target['window'])
                flags = link_flags(page.get('links') or [], target)
                if window or flags['exact_link'] or flags['encoded_link_only']:
                    counts[target['name']]['window_pages'] += window
                    kept[target['name'], page['url']] = {
                        'target': target['name'], 'url': page['url'], 'title': page.get('title'),
                        'pubdate': page.get('pubdate'), 'pubdate_source': page.get('pubdate_source'),
                        'in_window': window, **flags,
                        'title_mentions': window and bool(target['mention'].search(page.get('title') or ''))}
    return counts, kept, first, last, n_pages, n_bad


def scan_html(domain_dir, kept):
    """Add the HTML checks to the kept pages that have saved HTML. One Parquet file at a time, only the rows
    needed. Returns {target name: pages checked}."""
    targets_of = {}
    for name, url in kept:
        targets_of.setdefault(url, []).append(name)
    checked = Counter()
    for path in sorted(glob.glob(os.path.join(domain_dir, 'html', '*.parquet'))):
        urls = pq.read_table(path, columns=['url']).column('url').to_pylist()
        wanted = [i for i, url in enumerate(urls) if url in targets_of]
        if not wanted:
            continue
        table = pq.read_table(path, columns=['url', 'html']).take(wanted)
        for url, html in zip(table.column('url').to_pylist(), table.column('html').to_pylist()):
            text = ' '.join(TAGS.sub(' ', html.decode('utf-8', errors='replace')).split())
            for name in targets_of[url]:
                target = next(t for t in TARGETS if t['name'] == name)
                mention = target['mention'].search(text)
                page = kept[name, url]
                page['html_mentions'] = bool(mention)
                page['html_discusses'] = bool(mention) and bool(target['themes'].search(text))
                page['snippet'] = text[max(0, mention.start() - 60):mention.end() + 120] if mention else ''
                checked[name] += 1
        del table
    return checked


def main():
    sites, candidates = [], []
    domain_dirs = sorted(glob.glob(os.path.join(CRAWLS, '*')))
    started = time.time()
    for n, domain_dir in enumerate(domain_dirs, 1):
        domain = os.path.basename(domain_dir)
        path = os.path.join(domain_dir, 'pages.jsonl')
        print(f'[{time.time() - started:6.0f}s] site {n}/{len(domain_dirs)} {domain}: reading pages.jsonl', flush=True)
        if not os.path.exists(path):
            continue
        counts, kept, first, last, n_pages, n_bad = scan_pages(path)
        print(f'[{time.time() - started:6.0f}s]   {n_pages} pages; in the windows: '
              + ', '.join(f'{name} {c["window_pages"]}' for name, c in counts.items()) + '; scanning their HTML',
              flush=True)
        checked = scan_html(domain_dir, kept)
        for (name, _), page in kept.items():
            page['domain'] = domain
            if any(page.get(flag) for flag in FLAGS):
                candidates.append(page)
                counts[name].update({flag: 1 for flag in FLAGS if page.get(flag)})
        for name in counts:
            counts[name].update(pages=n_pages, bad_lines=n_bad, window_pages_with_html=checked[name])
        sites.append({'domain': domain, 'counts': counts, 'first': first, 'last': last,
                      'html_files': len(glob.glob(os.path.join(domain_dir, 'html', '*.parquet')))})
        print(f'[{time.time() - started:6.0f}s]   done: '
              + ', '.join(f'{name} {c["exact_link"]} links / {c["html_discusses"]} discussing'
                          for name, c in counts.items()), flush=True)
    with open('tmp.jsonl', 'w', encoding='utf-8') as f:
        for row in candidates:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    with open('tmp_report.md', 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(target_report(t, sites, candidates) for t in TARGETS) + '\n')
    print(f'\n-> tmp_report.md, tmp.jsonl ({len(candidates)} candidate pages)')


def target_report(target, sites, candidates):
    name, window = target['name'], target['window']
    total = Counter()
    for site in sites:
        total.update(site['counts'][name])
    lines = [f'# {name}: coverage of {target["url"]} ({window[0]} to {window[1]})', '',
             f'{len(sites)} sites, {total["pages"]} pages crawled ({total["bad_lines"]} unreadable lines skipped), '
             f'{total["window_pages"]} with a pubdate in the window, {total["window_pages_with_html"]} of them with '
             'saved HTML. (A site saves HTML 1000 pages at a time, so its newest pages have no HTML checks yet.)', '',
             f'- exact link: {total["exact_link"]}',
             f'- link found only after URL-decoding a redirect: {total["encoded_link_only"]}',
             f'- window page naming it in the title: {total["title_mentions"]}',
             f'- window page naming it in the text: {total["html_mentions"]}',
             f'- ...and one of its themes (discussing it): {total["html_discusses"]}',
             '', '| site | pages | window pages | w/ HTML | HTML files | pubdates | exact link | decoded link | title '
             '| text | discusses |', '|---|---|---|---|---|---|---|---|---|---|---|']
    for site in sorted(sites, key=lambda s: -s['counts'][name]['pages']):
        c = site['counts'][name]
        lines.append(f'| {site["domain"]} | {c["pages"]} | {c["window_pages"]} | {c["window_pages_with_html"]} | '
                     f'{site["html_files"]} | {site["first"]} – {site["last"]} | {c["exact_link"]} | '
                     f'{c["encoded_link_only"]} | {c["title_mentions"]} | {c["html_mentions"]} | '
                     f'{c["html_discusses"]} |')
    found = sorted((c for c in candidates if c['target'] == name),
                   key=lambda c: (not c.get('html_discusses'), c['pubdate'] or '', c['domain']))
    lines += ['', f'## Pages that link to it or name its subject ({len(found)}; discussing it first)', '']
    for c in found:
        how = ', '.join(flag for flag in FLAGS if c.get(flag))
        lines.append(f'- {(c["pubdate"] or "")[:10]} {c["domain"]} [{how}] {c["title"]}\n  {c["url"]}\n'
                     f'  > {c.get("snippet", "")}')
    return '\n'.join(lines)


if __name__ == '__main__':
    main()
