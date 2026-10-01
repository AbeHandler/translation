#!/usr/bin/env python
"""
Clean the collected English -> Chinese CC-NEWS links (src/en_zh_links.py): drop links whose fetch failed (error
pages labelled Chinese) and links from sources whose title is Chinese (mislabelled as English), and give every
row a story_id (syndicated copies of one story share it) and story_size (how many source articles it has).
Count and sample by story_id, not by article.
    data/processed/news_en_zh_links.jsonl -> data/processed/news_en_zh_links_clean.jsonl
Source titles are read from data/interim/cc_links (all ~21k links files: slow) and kept in -titles, so a rerun
only looks up sources it hasn't seen.

Run as a module from the repo root:
    python -m scripts.clean_en_zh_links
"""
import argparse
import glob
import json
import logging
import os
from collections import Counter
from urllib.parse import urlparse

from config.paths import CC_LINKS_DIR, NEWS_EN_ZH_LINKS_PATH
from src.en_zh_links import chinese_title, fetch_failed, source_titles, story_ids
from src.shard_queue.collect import write_jsonl


def parse_args():
    processed = os.path.dirname(NEWS_EN_ZH_LINKS_PATH)
    parser = argparse.ArgumentParser(description='Clean the English -> Chinese links')
    parser.add_argument('-links', default=str(NEWS_EN_ZH_LINKS_PATH), help='scripts/collect_queue.py output')
    parser.add_argument('-out', default=os.path.join(processed, 'news_en_zh_links_clean.jsonl'))
    parser.add_argument('-titles', default=os.path.join(processed, 'news_en_zh_source_titles.jsonl'),
                        help='cache of {url, title} for the source articles')
    parser.add_argument('-links-dir', default=str(CC_LINKS_DIR))
    return parser.parse_args()


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f]


def cached_titles(rows, titles_path, links_dir):
    """{srcpage: title}, from the cache, looking up (and caching) the sources not in it."""
    titles = {r['url']: r['title'] for r in read_jsonl(titles_path)}
    missing = {row['srcpage'] for row in rows} - set(titles)
    if missing:
        paths = sorted(p for p in glob.glob(os.path.join(links_dir, '*.jsonl')) if '.max' not in p)
        logging.info('looking up %d source titles in %d links files', len(missing), len(paths))
        titles.update({url: '' for url in missing})  # not found (e.g. links file gone) -> '', kept
        titles.update(source_titles(paths, missing))
        write_jsonl(({'url': url, 'title': title} for url, title in titles.items()), titles_path)
    return titles


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
    args = parse_args()
    rows = read_jsonl(args.links)
    titles = cached_titles(rows, args.titles, args.links_dir)
    dropped, kept = Counter(), []
    for row in rows:
        if fetch_failed(row):
            dropped[f"fetch failed ({row.get('status')})"] += 1
        elif chinese_title(titles.get(row['srcpage'])):
            dropped['Chinese source title'] += 1
        else:
            kept.append({**row, 'src_title': titles.get(row['srcpage'], '')})
    stories = story_ids(kept, titles)
    story_size = Counter(stories.values())
    for row in kept:
        row['story_id'] = stories[row['srcpage']]
        row['story_size'] = story_size[row['story_id']]
    write_jsonl(kept, args.out)
    print(f'{len(rows)} links -> {len(kept)} kept -> {args.out}')
    print(f"  {len({r['srcpage'] for r in kept})} source articles in {len(story_size)} stories")
    for reason, n in dropped.most_common():
        print(f'  {n:7d} dropped: {reason}')
    chinese_sources = Counter(urlparse(r['srcpage']).hostname for r in rows
                              if not fetch_failed(r) and chinese_title(titles.get(r['srcpage'])))
    print('\nsources dropped for Chinese titles, most links first:')
    for host, n in chinese_sources.most_common(10):
        print(f'  {n:7d}  {host}')
    print('\nmost syndicated stories (source articles):')
    for story, n in story_size.most_common(10):
        example = next(r for r in kept if r['story_id'] == story)
        print(f"  {n:5d}  {example['src_title'][:70] or example['srcpage'][:70]}")
    print('\nSpot checks:')
    print(f"  shuf -n 5 {args.out} | jq -c '{{src_title, url}}'")
    print(f"  jq -r 'select(.src_title == \"\") | .srcpage' {args.out} | wc -l   # sources with no title found")
    print(f"  jq -r 'select(.story_size > 1) | [.story_id, .srcpage] | @tsv' {args.out} | sort | head -20  # copies")


if __name__ == '__main__':
    main()
