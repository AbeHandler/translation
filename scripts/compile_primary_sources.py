#!/usr/bin/env python
"""
Compile the primary-source store (data/interim/primary/<sha1>.json, scripts/fetch_primary_sources.py) into one
Parquet file, a row per source: key, url, final_url, status, content_type, title, text, n_chars, fetched_at, error.
    data/interim/primary/*.json -> data/processed/primary.pq
Rebuilt whole each time. Each fetch worker also does this when it finishes (src/source_texts.py compile_store), so
the file stays current; run this by hand to rebuild it any time.

Run as a module from the repo root:
    python -m scripts.compile_primary_sources
"""
import argparse
from collections import Counter

from config.paths import PRIMARY_DB_PATH, PRIMARY_TEXTS_DIR
from src.source_texts import compile_store


def parse_args():
    parser = argparse.ArgumentParser(description='Compile the primary-source store into one Parquet file')
    parser.add_argument('-store-dir', default=str(PRIMARY_TEXTS_DIR))
    parser.add_argument('-out', default=str(PRIMARY_DB_PATH))
    return parser.parse_args()


def main():
    args = parse_args()
    rows = compile_store(args.store_dir, args.out)
    statuses = Counter(r['status'] for r in rows)
    print(f'{len(rows)} sources -> {args.out}; status: {dict(statuses.most_common(8))}; '
          f'{sum(1 for r in rows if r["status"] == 200 and (r["n_chars"] or 0) < 200)} fetched with < 200 characters')
    print(f'spot check: python -c "import pandas as pd; d = pd.read_parquet(\'{args.out}\'); '
          f'print(d[[\'url\', \'status\', \'n_chars\', \'title\']].sample(10))"')


if __name__ == '__main__':
    main()
