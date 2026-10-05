#!/usr/bin/env python
"""
Primary sources (src/primary_sources.py): the documents AI news links to that are not news coverage, from the
links themselves (no storms needed), ranked by how many outlets linked to them within 14 days of the first link.
    -step links    a worker: each corpus file's AI articles' links -> $DIR/links/<en|zh>__<file>.parquet
                   en: cc_links/<warc>.jsonl (AI articles: src/cc_news.py ai_article_links), dated by
                       cc_news_pubdates (or the WARC's date)
                   zh: media_storms_zh/links/<key>.jsonl (the Chinese AI pages), dated by media_storms_zh/days
    -step sources  all link rows -> data/processed/primary_sources.tsv
    -step flush    deletes $DIR
with $DIR = data/interim/primary_sources. links skips files already done, so rerun it as the corpora grow.

Run as a module from the repo root:
    python -m scripts.primary_sources -step links
    python -m scripts.primary_sources -step sources
"""
import argparse
import csv
import glob
import json
import os
import random
import re
import shutil

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from config.paths import (CC_HTML_DIR, CC_LINKS_DIR, CC_NEWS_PUBDATES_DIR, MEDIA_STORMS_ZH_DIR, PRIMARY_SOURCES_DIR,
                          PRIMARY_SOURCES_PATH)
from src.cc_news import ai_article_links
from src.file_worker import process_files
from src.primary_sources import LINK_SCHEMA, MIN_NEWS_ARTICLES, MIN_OUTLETS, link_rows, primary_sources
from src.warc_worker_cli import optional_int, setup_worker_process

COLUMNS = ['document', 'href', 'kind', 'first_seen', 'outlets_first', 'outlets', 'articles', 'en_outlets',
           'zh_outlets', 'example']
WARC_DATE = re.compile(r'CC-NEWS-(\d{4})(\d{2})(\d{2})')


def parse_args():
    parser = argparse.ArgumentParser(description='Primary sources from the links in AI news')
    parser.add_argument('-step', required=True, choices=('links', 'sources', 'flush'))
    parser.add_argument('-out-dir', default=str(PRIMARY_SOURCES_DIR))
    parser.add_argument('-cc-links-dir', default=str(CC_LINKS_DIR))
    parser.add_argument('-cc-html-dir', default=str(CC_HTML_DIR))
    parser.add_argument('-pubdates-dir', default=str(CC_NEWS_PUBDATES_DIR))
    parser.add_argument('-zh-dir', default=str(MEDIA_STORMS_ZH_DIR), help='the Chinese storms: links/ and days/')
    parser.add_argument('-out', default=str(PRIMARY_SOURCES_PATH))
    parser.add_argument('-min-outlets', type=int, default=MIN_OUTLETS)
    parser.add_argument('-min-news-articles', type=int, default=MIN_NEWS_ARTICLES,
                        help='a corpus site with this many AI articles is a news outlet')
    parser.add_argument('-max-files', type=optional_int, default=None, help='links: stop after N (testing)')
    return parser.parse_args()


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


def chinese_links(links_path, zh_dir):
    """Link rows of one crawl file's Chinese AI pages, dated by the zh storms' day files."""
    key = os.path.basename(links_path).removesuffix('.jsonl')
    dates = {}
    for path in glob.glob(os.path.join(zh_dir, 'days', '*', key + '.parquet')):
        date = os.path.basename(os.path.dirname(path))
        dates.update({url: date for url in pq.read_table(path, columns=['url']).column('url').to_pylist()})
    with open(links_path, encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            yield from link_rows(row['url'], [link['href'] for link in row['links']], dates.get(row['url'], ''), 'zh')


def links_step(args):
    links_dir = os.path.join(args.out_dir, 'links')
    os.makedirs(links_dir, exist_ok=True)
    inputs = [('en', p) for p in glob.glob(os.path.join(args.cc_links_dir, 'CC-NEWS-*.jsonl'))
              if re.fullmatch(r'CC-NEWS-\d+-\d+\.jsonl', os.path.basename(p))]
    inputs += [('zh', p) for p in glob.glob(os.path.join(args.zh_dir, 'links', '*.jsonl'))]
    random.shuffle(inputs)
    language_of = dict((p, lang) for lang, p in inputs)

    def out_path(path):
        return os.path.join(links_dir, f'{language_of[path]}__{os.path.basename(path).removesuffix(".jsonl")}.parquet')

    def extract(path, out):
        rows = list(english_links(path, args.cc_html_dir, args.pubdates_dir) if language_of[path] == 'en'
                    else chinese_links(path, args.zh_dir))
        pq.write_table(pa.Table.from_pylist(rows, LINK_SCHEMA), out + '.part')
        os.rename(out + '.part', out)
        return {'links': len(rows)}
    process_files([p for _, p in inputs], out_path, extract, args.max_files)


def sources_step(args):
    table = ds.dataset(os.path.join(args.out_dir, 'links'), format='parquet').to_table()
    volume = table.select(['outlet', 'article']).group_by('outlet').aggregate([('article', 'count_distinct')])
    outlets = set(volume.filter(pc.greater_equal(volume['article_count_distinct'], args.min_news_articles))
                  ['outlet'].to_pylist())
    counts = table.group_by('document').aggregate([('outlet', 'count_distinct')])
    keep = counts.filter(pc.greater_equal(counts['outlet_count_distinct'], args.min_outlets))['document']
    rows = table.filter(pc.is_in(table['document'], keep)).to_pylist()
    print(f'{table.num_rows} links from {volume.num_rows} sites, {len(outlets)} of them news outlets '
          f'(>= {args.min_news_articles} AI articles); {len(keep)} documents linked by >= {args.min_outlets} outlets',
          flush=True)
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
