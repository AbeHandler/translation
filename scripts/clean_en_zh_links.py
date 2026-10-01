#!/usr/bin/env python
"""
Clean the collected English -> Chinese CC-NEWS links (src/en_zh_links.py): drop links whose fetch failed (error
pages labelled Chinese), links from sources whose title is Chinese (mislabelled as English) and from sources
whose article body says "AI" fewer than -min-body-ai times (not about AI: "AI" only in menus or sidebars), and
give every
row a story_id (syndicated copies of one story share it), story_size (how many source articles it has) and
is_press_release (the source is a press-release wire or a wire copy).
Count and sample by story_id, not by article.
    data/processed/news_en_zh_links.jsonl -> data/processed/news_en_zh_links_clean.jsonl
Source info (title, links file, body "AI" count) is read from data/interim/cc_links (all ~21k links files: slow)
plus, for links files older than the body count, from the articles' HTML in data/interim/cc_html, and kept in
-sources, so a rerun only looks up sources it hasn't seen.

Run as a module from the repo root:
    python -m scripts.clean_en_zh_links
"""
import argparse
import glob
import json
import logging
import os
from collections import Counter, defaultdict
from urllib.parse import urlparse

from config.paths import CC_HTML_DIR, CC_LINKS_DIR, NEWS_EN_ZH_LINKS_PATH
from src.en_zh_links import (body_ai_mentions, chinese_title, fetch_failed, is_press_release, source_info,
                             story_ids)
from src.shard_queue.collect import write_jsonl


def parse_args():
    processed = os.path.dirname(NEWS_EN_ZH_LINKS_PATH)
    parser = argparse.ArgumentParser(description='Clean the English -> Chinese links')
    parser.add_argument('-links', default=str(NEWS_EN_ZH_LINKS_PATH), help='scripts/collect_queue.py output')
    parser.add_argument('-out', default=os.path.join(processed, 'news_en_zh_links_clean.jsonl'))
    parser.add_argument('-sources', default=os.path.join(processed, 'news_en_zh_sources.jsonl'),
                        help='cache of {url, title, links_file, body_ai_mentions} for the source articles')
    parser.add_argument('-links-dir', default=str(CC_LINKS_DIR))
    parser.add_argument('-html-dir', default=str(CC_HTML_DIR), help="the articles' HTML, for old links files")
    parser.add_argument('-min-body-ai', type=int, default=1, help='"AI" at least this often in the article body')
    return parser.parse_args()


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f]


def cached_sources(rows, sources_path, links_dir, html_dir):
    """{srcpage: {title, links_file, body_ai_mentions}}, from the cache, looking up (and caching) the rest."""
    sources = {r['url']: r for r in read_jsonl(sources_path)}
    missing = {row['srcpage'] for row in rows} - set(sources)
    if missing:
        paths = sorted(p for p in glob.glob(os.path.join(links_dir, '*.jsonl')) if '.max' not in p)
        logging.info('looking up %d sources in %d links files', len(missing), len(paths))
        found = source_info(paths, missing)
        for url in missing:  # not found (e.g. links file gone): kept, unfiltered
            sources[url] = {'url': url, 'title': '', 'links_file': None, 'body_ai_mentions': None,
                            **found.get(url, {})}
    uncounted = defaultdict(set)  # links file -> sources whose body "AI" count isn't known yet
    for url, source in sources.items():
        if source['body_ai_mentions'] is None and source['links_file']:
            uncounted[source['links_file']].add(url)
    for n, (links_file, urls) in enumerate(sorted(uncounted.items()), 1):
        html_path = os.path.join(html_dir, links_file.removesuffix('.jsonl') + '.parquet')
        if os.path.exists(html_path):
            for url, count in body_ai_mentions(html_path, urls).items():
                sources[url]['body_ai_mentions'] = count
        if n % 500 == 0 or n == len(uncounted):
            logging.info('body "AI" counted from HTML: %d/%d files', n, len(uncounted))
    if missing or uncounted:
        write_jsonl(sources.values(), sources_path)
    return sources


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
    args = parse_args()
    rows = read_jsonl(args.links)
    sources = cached_sources(rows, args.sources, args.links_dir, args.html_dir)
    titles = {url: source['title'] for url, source in sources.items()}
    dropped, kept = Counter(), []
    for row in rows:
        body_ai = sources[row['srcpage']]['body_ai_mentions']
        if fetch_failed(row):
            dropped[f"fetch failed ({row.get('status')})"] += 1
        elif chinese_title(titles.get(row['srcpage'])):
            dropped['Chinese source title'] += 1
        elif body_ai is not None and body_ai < args.min_body_ai:
            dropped[f'"AI" fewer than {args.min_body_ai} times in the source\'s body'] += 1
        else:
            kept.append({**row, 'src_title': titles.get(row['srcpage'], ''), 'src_body_ai_mentions': body_ai})
    stories = story_ids(kept, titles)
    story_size = Counter(stories.values())
    for row in kept:
        row['story_id'] = stories[row['srcpage']]
        row['story_size'] = story_size[row['story_id']]
        row['is_press_release'] = is_press_release(row['srcpage'])
    write_jsonl(kept, args.out)
    print(f'{len(rows)} links -> {len(kept)} kept -> {args.out}')
    print(f"  {len({r['srcpage'] for r in kept})} source articles in {len(story_size)} stories, "
          f"{len({r['story_id'] for r in kept if r['is_press_release']})} of them press releases")
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
    print(f"  jq -c 'select(.is_press_release | not)' {args.out} | wc -l   # links not from press releases")


if __name__ == '__main__':
    main()
