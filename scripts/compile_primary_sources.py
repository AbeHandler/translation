#!/usr/bin/env python
"""
Compile the primary-source store (data/interim/primary/<sha1>.json, scripts/fetch_primary_sources.py) into one
Parquet file, a row per source: key, url, final_url, status, content_type, title, text, n_chars, fetched_at, error.
    data/interim/primary/*.json -> data/processed/primary.pq
Rebuilt whole each time, so run it after the fetch workers (scripts/fetch_primary_sources.sh does).

Run as a module from the repo root:
    python -m scripts.compile_primary_sources
"""
import argparse
import glob
import json
import os
from collections import Counter

import pyarrow as pa
import pyarrow.parquet as pq

from config.paths import PRIMARY_DB_PATH, PRIMARY_TEXTS_DIR

SCHEMA = pa.schema([('key', pa.string()), ('url', pa.string()), ('final_url', pa.string()), ('status', pa.int32()),
                    ('content_type', pa.string()), ('title', pa.string()), ('text', pa.string()),
                    ('n_chars', pa.int32()), ('fetched_at', pa.string()), ('error', pa.string())])


def parse_args():
    parser = argparse.ArgumentParser(description='Compile the primary-source store into one Parquet file')
    parser.add_argument('-store-dir', default=str(PRIMARY_TEXTS_DIR))
    parser.add_argument('-out', default=str(PRIMARY_DB_PATH))
    return parser.parse_args()


def main():
    args = parse_args()
    rows = []
    for path in glob.glob(os.path.join(args.store_dir, '*.json')):
        with open(path, encoding='utf-8') as f:
            source = json.load(f)
        rows.append({name: source.get(name) for name in SCHEMA.names})
    rows.sort(key=lambda r: r['url'] or '')
    pq.write_table(pa.Table.from_pylist(rows, SCHEMA), args.out + '.part', compression='zstd')
    os.replace(args.out + '.part', args.out)
    statuses = Counter(r['status'] for r in rows)
    print(f'{len(rows)} sources -> {args.out}; status: {dict(statuses.most_common(8))}; '
          f'{sum(1 for r in rows if r["status"] == 200 and (r["n_chars"] or 0) < 200)} fetched with < 200 characters')
    print(f'spot check: python -c "import pandas as pd; d = pd.read_parquet(\'{args.out}\'); '
          f'print(d[[\'url\', \'status\', \'n_chars\', \'title\']].sample(10))"')


if __name__ == '__main__':
    main()
