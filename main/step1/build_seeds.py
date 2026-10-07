#!/usr/bin/env python
"""
Step 1: the seeds and their raw text (model.md, Seeds; src/seeds.py).
  1. The seed table: from the inbound links that AI news makes to documents, English (CC-NEWS) and Chinese (the
     site crawls), the primary sources linked by -min-outlets+ outlets in either language, plus the seeds in
     config/seeds_extra.tsv (one URL per line, added by hand).
  2. Their raw text: the seeds are added to the primary-source store's to-do list (data/interim/primary/todo.tsv),
     those without a stored text are fetched (-threads at once; src/source_texts.py), and the store is compiled
     into data/processed/primary.pq.
  3. A report: seeds by kind, origin and organisation, and how many have their text.
    data/interim/primary_sources{,_zh}/links/ (scripts/primary_sources.py -step links) + config/seeds_extra.tsv
        -> data/processed/seeds.tsv, data/interim/primary/, data/processed/primary.pq
One row per seed: seed_id, url, key, kind, organisation, first_seen, outlets, outlets_first (both languages), per
language en_/zh_ outlets, outlets_first (within 14 days of the first link), first_seen, an example article; and
text_status (text, short, failed, not fetched), n_chars, title. -retry-failed fetches failed seeds again.

Run as a module from the repo root:
    python -m main.step1.build_seeds
    python -m main.step1.build_seeds -min-outlets 10
    python -m main.step1.build_seeds -no-fetch        # the table and report only
"""
import argparse
import csv
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from config.paths import PRIMARY_DB_PATH, PRIMARY_SOURCES_DIR, PRIMARY_TEXTS_DIR, SEEDS_EXTRA_PATH, SEEDS_PATH
from src.primary_sources import MIN_NEWS_ARTICLES, MIN_OUTLETS, sources_from_link_tables
from src.seeds import COLUMNS, add_text_status, merge_seeds
from src.source_texts import SourceFetcher, add_to_todo, compile_store, source_path, store_source


def parse_args():
    parser = argparse.ArgumentParser(description='Build the seed table from the inbound links of AI news')
    parser.add_argument('-en-links', default=os.path.join(str(PRIMARY_SOURCES_DIR), 'links'))
    parser.add_argument('-zh-links', default=os.path.join(str(PRIMARY_SOURCES_DIR) + '_zh', 'links'))
    parser.add_argument('-extra', default=str(SEEDS_EXTRA_PATH), help='hand-picked seeds, one URL per line')
    parser.add_argument('-min-outlets', type=int, default=5, help='outlets linking it, in either language')
    parser.add_argument('-min-news-articles', type=int, default=MIN_NEWS_ARTICLES, help='en: a news outlet')
    parser.add_argument('-out', default=str(SEEDS_PATH))
    parser.add_argument('-store-dir', default=str(PRIMARY_TEXTS_DIR), help='the primary-source store')
    parser.add_argument('-db', default=str(PRIMARY_DB_PATH), help='the store compiled into one table')
    parser.add_argument('-threads', type=int, default=16, help='seeds fetched at once')
    parser.add_argument('-no-fetch', action='store_true', help="don't fetch: the table and report only")
    parser.add_argument('-retry-failed', action='store_true', help='fetch seeds whose fetch failed again')
    return parser.parse_args()


def sources(links_dir, corpus, args):
    if not os.path.isdir(links_dir):
        raise FileNotFoundError(f'{links_dir} missing: run scripts/go_primary_sources.sh'
                                + (' with CORPUS=zh' if corpus == 'zh' else ''))
    found, summary = sources_from_link_tables(links_dir, corpus, min(args.min_outlets, MIN_OUTLETS),
                                              args.min_news_articles)
    print(summary, flush=True)
    return found


def stored(store_dir, url):
    """The store's row for url, or None."""
    path = source_path(store_dir, url)
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def fetch_seed_texts(seeds, args):
    """Add the seeds to the store's to-do list, fetch those without a stored text, compile the store."""
    os.makedirs(args.store_dir, exist_ok=True)
    added = add_to_todo(os.path.join(args.store_dir, 'todo.tsv'), (s['url'] for s in seeds))
    todo = [s['url'] for s in seeds if (got := stored(args.store_dir, s['url'])) is None
            or (args.retry_failed and got['status'] != 200)]
    print(f'{added} seeds added to the to-do list; fetching {len(todo)} without a stored text', flush=True)
    fetcher = SourceFetcher()
    with ThreadPoolExecutor(args.threads) as pool:
        for n, row in enumerate(pool.map(lambda url: store_source(fetcher, url, args.store_dir), todo), 1):
            if n % 200 == 0 or n == len(todo):
                print(f'  {n}/{len(todo)} fetched', flush=True)
    rows = compile_store(args.store_dir, args.db)
    print(f'{len(rows)} sources in {args.db}', flush=True)


def report(seeds):
    status = Counter(s['text_status'] for s in seeds)
    print(f'\n{len(seeds)} seeds; raw text for {status["text"]} ({status["text"] / max(len(seeds), 1):.0%}); '
          f'{dict(status)}')
    print('by where they came from:', dict(Counter(s['added_from'] for s in seeds)))
    print('text by kind:')
    for kind, n in Counter(s['kind'] for s in seeds).most_common():
        have = sum(1 for s in seeds if s['kind'] == kind and s['text_status'] == 'text')
        print(f'  {kind:16} {have:6d} of {n:6d} with text')
    print('top organisations:', Counter(s['organisation'] for s in seeds).most_common(15))
    print('\nmost linked (outlets in the first 14 days, en + zh):')
    for s in seeds[:25]:
        print(f"  {s['outlets_first']:4d} ({s['en_outlets_first']} en, {s['zh_outlets_first']} zh)  {s['first_seen']}  "
              f"{s['text_status']:11} {s['url'][:80]}")


def main():
    args = parse_args()
    en = sources(args.en_links, 'en', args)
    zh = sources(args.zh_links, 'zh', args)
    manual = []
    if os.path.exists(args.extra):
        with open(args.extra, encoding='utf-8') as f:
            manual = [line.split('#')[0].strip() for line in f if line.split('#')[0].strip()]
    seeds = merge_seeds(en, zh, manual, args.min_outlets)
    if not args.no_fetch:
        fetch_seed_texts(seeds, args)
    add_text_status(seeds, {s['key']: got for s in seeds if (got := stored(args.store_dir, s['url']))})
    with open(args.out + '.part', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, COLUMNS, delimiter='\t')
        writer.writeheader()
        writer.writerows(seeds)
    os.replace(args.out + '.part', args.out)
    print(f'{len(seeds)} seeds -> {args.out}')
    report(seeds)
    print(f'\nspot check: awk -F"\\t" \'$16 != "text"\' {args.out} | cut -f2,16,17 | head    # seeds without text')


if __name__ == '__main__':
    main()
