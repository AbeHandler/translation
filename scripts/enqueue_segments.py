#!/usr/bin/env python
"""
Add segments from a CSV (seg_id, src_lang, tgt_lang, text[, context_before, context_after]) to the MT queue
in data/processed/translations.sqlite. Segments already queued are skipped, so it is safe to rerun; a seg_id
queued with different text is an error. scripts/run_translations.py then translates the queue.

Run as a module from the repo root:
    python -m scripts.enqueue_segments -segments segments.csv
"""
import argparse
import os

from config.paths import TRANSLATIONS_DB
from src.translation.segments import read_segments
from src.translation.store import TranslationStore


def parse_args():
    parser = argparse.ArgumentParser(description='Add segments from a CSV to the MT queue')
    parser.add_argument('-segments', required=True, help='CSV: seg_id, src_lang, tgt_lang, text[, context_*]')
    parser.add_argument('-source', default='', help='where the segments came from (default: the CSV file name)')
    parser.add_argument('-db', default=str(TRANSLATIONS_DB))
    return parser.parse_args()


def main():
    args = parse_args()
    store = TranslationStore(args.db)
    added, already = store.enqueue(read_segments(args.segments), args.source or os.path.basename(args.segments))
    total = store.db.execute('SELECT COUNT(*) FROM queue').fetchone()[0]
    print(f'{added} segments added, {already} already queued; {total} in the queue ({args.db})')
    print(f'Spot check:\n  sqlite3 {args.db} "SELECT source, COUNT(*) FROM queue GROUP BY source"')
    store.close()


if __name__ == '__main__':
    main()
