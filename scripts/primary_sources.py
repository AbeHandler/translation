#!/usr/bin/env python
"""
Primary sources (src/primary_sources.py): the documents AI news links to that are not news coverage, from the
links themselves (no storms needed), ranked by how many outlets linked to them within 14 days of the first link.
One corpus per run:
    -corpus en   English CC-NEWS: cc_links/<warc>.jsonl (AI articles: src/cc_news.py ai_article_links), dated by
                 cc_news_pubdates (or the WARC's date)  -> $DIR = data/interim/primary_sources,
                 data/processed/primary_sources.tsv; a site is a news outlet with -min-news-articles AI articles
    -corpus zh   the Chinese site crawls: site_crawls/<domain>/html/*.parquet, pages about AI (config/
                 chinese_ai_terms.txt), their body links, dated from the HTML -> $DIR = data/interim/
                 primary_sources_zh, data/processed/primary_sources_zh.tsv; every crawled site is a news outlet
Steps:
    -step links    a worker: each corpus file's link rows -> $DIR/links/<file>.parquet
    -step sources  all link rows -> the TSV
    -step flush    deletes $DIR
links skips files already done, so rerun it as the corpora grow.

Run as a module from the repo root:
    python -m scripts.primary_sources -step links
    python -m scripts.primary_sources -step sources
    python -m scripts.primary_sources -corpus zh -step links
"""
import argparse
import csv
import datetime
import glob
import logging
import os
import random
import re
import shutil

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from config.paths import (CC_HTML_DIR, CC_LINKS_DIR, CC_NEWS_PUBDATES_DIR, PRIMARY_SOURCES_DIR, PRIMARY_SOURCES_PATH,
                          SITE_CRAWLS_DIR)
from src.cc_news import ai_article_links
from src.file_worker import process_files
from src.primary_sources import (LINK_SCHEMA, MIN_NEWS_ARTICLES, MIN_OUTLETS, NEWS_DOMAINS_ZH, chinese_page_links,
                                 link_rows, primary_sources)
from src.warc_worker_cli import optional_int, setup_worker_process

COLUMNS = ['document', 'href', 'kind', 'first_seen', 'outlets_first', 'outlets', 'articles', 'en_outlets',
           'zh_outlets', 'example']
WARC_DATE = re.compile(r'CC-NEWS-(\d{4})(\d{2})(\d{2})')


def parse_args():
    parser = argparse.ArgumentParser(description='Primary sources from the links in AI news')
    parser.add_argument('-step', required=True, choices=('links', 'sources', 'flush'))
    parser.add_argument('-corpus', default='en', choices=('en', 'zh'))
    parser.add_argument('-out-dir', default=None, help='default: by corpus')
    parser.add_argument('-cc-links-dir', default=str(CC_LINKS_DIR))
    parser.add_argument('-cc-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-pubdates-dir', default=str(CC_NEWS_PUBDATES_DIR))
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR), help='zh: <domain>/html/*.parquet')
    parser.add_argument('-out', default=None, help='default: by corpus')
    parser.add_argument('-min-outlets', type=int, default=MIN_OUTLETS)
    parser.add_argument('-min-news-articles', type=int, default=MIN_NEWS_ARTICLES,
                        help='a corpus site with this many AI articles is a news outlet')
    parser.add_argument('-max-files', type=optional_int, default=None, help='links: stop after N (testing)')
    args = parser.parse_args()
    zh = args.corpus == 'zh'
    args.out_dir = args.out_dir or str(PRIMARY_SOURCES_DIR) + ('_zh' if zh else '')
    args.out = args.out or str(PRIMARY_SOURCES_PATH).replace('.tsv', '_zh.tsv' if zh else '.tsv')
    return args


def english_links(links_path, html_dir, pubdates_dir):
    """Link rows of one WARC's AI articles."""
    warc = os.path.basename(links_path).removesuffix('.jsonl')
    dates_path = os.path.join(pubdates_dir, warc + '.parquet')
    dates = {}
    if os.path.exists(dates_path):
        dates = dict(zip(*pq.read_table(dates_path, columns=['url', 'date']).to_pydict().values()))
    match = WARC_DATE.search(warc)
    warc_date = f'{match.group(1)}-{match.group(2)}-{match.group(3)}' if match else ''
    by_article = {}
    for row in ai_article_links(os.path.join(html_dir, warc + '.parquet'), links_path):
        if row['src_language'] == 'en':
            by_article.setdefault(row['srcpage'], []).append(row['url'])
    for article, hrefs in by_article.items():
        yield from link_rows(article, hrefs, (dates.get(article) or warc_date)[:10], 'en')


def chinese_links(html_path, last_day):
    """Link rows of one crawl file's Chinese AI pages."""
    for batch in pq.ParquetFile(html_path).iter_batches(batch_size=200, columns=['url', 'language', 'html']):
        for row in batch.to_pylist():
            try:
                found = chinese_page_links(row, last_day)
            except Exception:   # one unparseable page shouldn't lose the file's other pages
                logging.exception('skipping %s', row['url'])
                continue
            if found:
                yield from link_rows(row['url'], found[1], found[0], 'zh')


def links_step(args):
    links_dir = os.path.join(args.out_dir, 'links')
    os.makedirs(links_dir, exist_ok=True)
    if args.corpus == 'en':
        paths = [p for p in glob.glob(os.path.join(args.cc_links_dir, 'CC-NEWS-*.jsonl'))
                 if re.fullmatch(r'CC-NEWS-\d+-\d+\.jsonl', os.path.basename(p))]

        def name(path):
            return os.path.basename(path).removesuffix('.jsonl')

        def rows_of(path):
            return english_links(path, args.cc_html_dir, args.pubdates_dir)
    else:
        paths = glob.glob(os.path.join(args.crawls_dir, '*', 'html', '*.parquet'))
        last_day = datetime.date.today().isoformat()

        def name(path):   # <domain>__<part>
            return os.path.basename(os.path.dirname(os.path.dirname(path))) + '__' + \
                os.path.basename(path).removesuffix('.parquet')

        def rows_of(path):
            return chinese_links(path, last_day)
    random.shuffle(paths)

    def extract(path, out):
        rows = list(rows_of(path))
        pq.write_table(pa.Table.from_pylist(rows, LINK_SCHEMA), out + '.part')
        os.rename(out + '.part', out)
        return {'links': len(rows)}
    process_files(paths, lambda p: os.path.join(links_dir, name(p) + '.parquet'), extract, args.max_files)


def sources_step(args):
    table = ds.dataset(os.path.join(args.out_dir, 'links'), format='parquet').to_table()
    volume = table.select(['outlet', 'article']).group_by('outlet').aggregate([('article', 'count_distinct')])
    if args.corpus == 'zh':   # the crawled sites are news outlets we chose, whatever their volume
        outlets = set(volume['outlet'].to_pylist()) | NEWS_DOMAINS_ZH
    else:
        outlets = set(volume.filter(pc.greater_equal(volume['article_count_distinct'], args.min_news_articles))
                      ['outlet'].to_pylist())
    counts = table.group_by('document').aggregate([('outlet', 'count_distinct')])
    keep = counts.filter(pc.greater_equal(counts['outlet_count_distinct'], args.min_outlets))['document']
    rows = table.filter(pc.is_in(table['document'], keep)).to_pylist()
    rule = 'every crawled site and major portal' if args.corpus == 'zh' else f'>= {args.min_news_articles} AI articles'
    print(f'{table.num_rows} links from {volume.num_rows} sites, {len(outlets)} news outlets ({rule}); '
          f'{len(keep)} documents linked by >= {args.min_outlets} outlets', flush=True)
    found = primary_sources(rows, outlets, min_outlets=args.min_outlets)
    with open(args.out + '.part', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, COLUMNS, delimiter='\t')
        writer.writeheader()
        writer.writerows(found)
    os.rename(args.out + '.part', args.out)
    print(f'{len(found)} primary sources -> {args.out}')
    for s in found[:25]:
        print(f"  {s['outlets_first']:4d} outlets in 14 days ({s['en_outlets']} en, {s['zh_outlets']} zh)  "
              f"{s['first_seen']}  {s['kind']:15} {s['href'][:80]}")
    print(f'spot check: cut -f3 {args.out} | sort | uniq -c;  grep -P "\\tgovernment\\t" {args.out} | head')


def flush_step(args):
    """FLUSH: deletes everything under out_dir, files in random order."""
    paths = [os.path.join(root, name) for root, _, names in os.walk(args.out_dir) for name in names]
    random.shuffle(paths)
    for path in paths:
        os.remove(path)
    shutil.rmtree(args.out_dir, ignore_errors=True)
    print(f'deleted {len(paths)} files in {args.out_dir}')


def main():
    setup_worker_process()
    args = parse_args()
    {'links': links_step, 'sources': sources_step, 'flush': flush_step}[args.step](args)


if __name__ == '__main__':
    main()
