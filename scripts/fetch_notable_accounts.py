#!/usr/bin/env python
"""
Download the notable X/Twitter accounts from Wikidata (src/notable_accounts.py: every item with an X username, its
name, Wikipedia count, person or not) -> data/external/notable_accounts.tsv. Skipped if it exists (-force refetches).

Run as a module from the repo root:
    python -m scripts.fetch_notable_accounts
"""
import argparse
import csv
import os

import httpx

from config.paths import NOTABLE_ACCOUNTS_PATH
from src.notable_accounts import COLUMNS, WIKIDATA_QUERY, parse_wikidata_tsv

ENDPOINT = 'https://qlever.cs.uni-freiburg.de/api/wikidata'


def parse_args():
    parser = argparse.ArgumentParser(description='Download the notable X accounts from Wikidata')
    parser.add_argument('-out', default=str(NOTABLE_ACCOUNTS_PATH))
    parser.add_argument('-force', action='store_true')
    return parser.parse_args()


def main():
    args = parse_args()
    if os.path.exists(args.out) and not args.force:
        print(f'{args.out} exists; -force to refetch')
        return
    response = httpx.get(ENDPOINT, params={'query': WIKIDATA_QUERY}, headers={'Accept': 'text/tab-separated-values'},
                         follow_redirects=True, timeout=600)
    response.raise_for_status()
    rows = list(parse_wikidata_tsv(response.text))
    if len(rows) < 100_000:
        raise RuntimeError(f'only {len(rows)} accounts from Wikidata; expected ~465K')
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out + '.part', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, COLUMNS, delimiter='\t')
        writer.writeheader()
        writer.writerows({**r, 'human': str(r['human']).lower()} for r in rows)
    os.rename(args.out + '.part', args.out)
    print(f'{len(rows)} accounts ({sum(r["sitelinks"] > 0 for r in rows)} with a Wikipedia article) -> {args.out}')
    print(f'spot check: grep -P "^(sama|karpathy|reidhoffman)\\t" {args.out}')


if __name__ == '__main__':
    main()
