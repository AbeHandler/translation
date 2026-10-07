#!/usr/bin/env python
"""
Step 1: the seed table (model.md, Seeds; src/seeds.py). From the inbound links that AI news makes to documents,
English (CC-NEWS) and Chinese (the site crawls), the primary sources linked by -min-outlets+ outlets in either
language, plus the seeds in config/seeds_extra.tsv (one URL per line, added by hand):
    data/interim/primary_sources/links/ + data/interim/primary_sources_zh/links/ (scripts/primary_sources.py
    -step links) + config/seeds_extra.tsv -> data/processed/seeds.tsv
One row per seed: seed_id, url, key, kind, organisation, first_seen, outlets, outlets_first (both languages), and
per language en_/zh_ outlets, outlets_first (within 14 days of the first link), first_seen, an example article.

Run as a module from the repo root:
    python -m main.step1.build_seeds
    python -m main.step1.build_seeds -min-outlets 10
"""
import argparse
import csv
import os
from collections import Counter

from config.paths import PRIMARY_SOURCES_DIR, SEEDS_EXTRA_PATH, SEEDS_PATH
from src.primary_sources import MIN_NEWS_ARTICLES, MIN_OUTLETS, sources_from_link_tables
from src.seeds import COLUMNS, merge_seeds


def parse_args():
    parser = argparse.ArgumentParser(description='Build the seed table from the inbound links of AI news')
    parser.add_argument('-en-links', default=os.path.join(str(PRIMARY_SOURCES_DIR), 'links'))
    parser.add_argument('-zh-links', default=os.path.join(str(PRIMARY_SOURCES_DIR) + '_zh', 'links'))
    parser.add_argument('-extra', default=str(SEEDS_EXTRA_PATH), help='hand-picked seeds, one URL per line')
    parser.add_argument('-min-outlets', type=int, default=5, help='outlets linking it, in either language')
    parser.add_argument('-min-news-articles', type=int, default=MIN_NEWS_ARTICLES, help='en: a news outlet')
    parser.add_argument('-out', default=str(SEEDS_PATH))
    return parser.parse_args()


def sources(links_dir, corpus, args):
    if not os.path.isdir(links_dir):
        raise FileNotFoundError(f'{links_dir} missing: run scripts/go_primary_sources.sh'
                                + (' with CORPUS=zh' if corpus == 'zh' else ''))
    found, summary = sources_from_link_tables(links_dir, corpus, min(args.min_outlets, MIN_OUTLETS),
                                              args.min_news_articles)
    print(summary, flush=True)
    return found


def main():
    args = parse_args()
    en = sources(args.en_links, 'en', args)
    zh = sources(args.zh_links, 'zh', args)
    manual = []
    if os.path.exists(args.extra):
        with open(args.extra, encoding='utf-8') as f:
            manual = [line.split('#')[0].strip() for line in f if line.split('#')[0].strip()]
    seeds = merge_seeds(en, zh, manual, args.min_outlets)
    with open(args.out + '.part', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, COLUMNS, delimiter='\t')
        writer.writeheader()
        writer.writerows(seeds)
    os.replace(args.out + '.part', args.out)
    print(f'{len(seeds)} seeds -> {args.out}')
    print('by where they came from:', dict(Counter(s['added_from'] for s in seeds)))
    print('by kind:', dict(Counter(s['kind'] for s in seeds)))
    print('top organisations:', Counter(s['organisation'] for s in seeds).most_common(15))
    print('\nmost linked (outlets in the first 14 days, en + zh):')
    for s in seeds[:25]:
        print(f"  {s['outlets_first']:4d} ({s['en_outlets_first']} en, {s['zh_outlets_first']} zh)  {s['first_seen']}  "
              f"{s['kind']:15} {s['url'][:80]}")
    print(f'spot check: awk -F"\\t" \'$12 > 0 && $9 > 0\' {args.out} | cut -f2,9,12 | head    # seeds in both')


if __name__ == '__main__':
    main()
