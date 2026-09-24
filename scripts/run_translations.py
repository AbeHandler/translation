#!/usr/bin/env python
"""
Driver: run source segments through several MT engines and store every call in SQLite
(src/translation; the store's docstring has the tables).

    segments CSV (seg_id, src_lang, tgt_lang, text[, context_before, context_after])
        -> data/processed/translations.sqlite

Calls already stored successfully are skipped, so a rerun costs nothing and adding an engine only pays for
that engine. Calls run in random order. API keys come from environment variables (see
src/translation/backends.py); a missing one stops the run before any call.

Run as a module from the repo root, so `src` and `config` import:
    python -m scripts.run_translations -segments segments.csv -dry-run
    python -m scripts.run_translations -segments segments.csv
    python -m scripts.run_translations -segments segments.csv -engines google_nmt deepseek -n-samples 3
"""
import argparse
import logging
from collections import Counter

from config.paths import TRANSLATIONS_DB
from src.translation.backends import ENGINES, build_engines
from src.translation.runner import plan_calls, run_translations
from src.translation.segments import CONTEXT_MODES, read_segments
from src.translation.store import TranslationStore


def parse_args():
    parser = argparse.ArgumentParser(description='Translate segments with several MT engines into SQLite')
    parser.add_argument('-segments', required=True, help='CSV: seg_id, src_lang, tgt_lang, text[, context_*]')
    parser.add_argument('-db', default=str(TRANSLATIONS_DB))
    parser.add_argument('-engines', nargs='+', default=['google_nmt', 'baidu', 'deepseek', 'openai'],
                        choices=sorted(ENGINES),
                        help='default (paper 1): Google NMT, Baidu, one Chinese LLM, one Western LLM')
    parser.add_argument('-context-modes', nargs='+', default=list(CONTEXT_MODES), choices=CONTEXT_MODES)
    parser.add_argument('-n-samples', type=int, default=5, help='samples per LLM engine; NMT engines run once')
    parser.add_argument('-temperature', type=float, default=0.7, help='LLM temperature; 0 collapses the samples')
    parser.add_argument('-delay', type=float, default=0.4, help='seconds between calls')
    parser.add_argument('-dry-run', action='store_true', help='print the call plan, call nothing')
    return parser.parse_args()


def print_plan(calls):
    """Planned calls and source characters per engine (dry run)."""
    n_calls = Counter(f'{c.engine.name}/{c.engine.model}' for c in calls)
    n_chars = Counter()
    for call in calls:
        n_chars[f'{call.engine.name}/{call.engine.model}'] += len(call.source_text)
    for engine, n in sorted(n_calls.items()):
        print(f'  {engine:32} {n:6} calls  {n_chars[engine]:9} source chars')
    print(f'  {"total":32} {len(calls):6} calls')


def main():
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    segments = read_segments(args.segments)
    engines = build_engines(args.engines)
    calls = plan_calls(segments, engines, args.context_modes, args.n_samples)
    print(f'{len(segments)} segments, engines {", ".join(args.engines)}, modes {", ".join(args.context_modes)}')
    if args.dry_run:
        print_plan(calls)
        return
    store = TranslationStore(args.db)
    run_id = store.start_run(vars(args))
    counts = run_translations(calls, store, run_id, args.temperature, args.delay)
    print(f'\nrun {run_id}: {counts} -> {args.db}')
    print('\nDistinct isolated translations per segment (across engines and samples):')
    for seg_id, n in store.distinct_translations('isolated').items():
        print(f'  {seg_id}: {n}{"   <-- converged" if n == 1 else ""}')
    print('\nSpot checks:')
    print(f'  sqlite3 {args.db} "SELECT engine, model, context_mode, COUNT(*), SUM(error IS NOT NULL) '
          'FROM calls GROUP BY 1, 2, 3"')
    print(f'  sqlite3 {args.db} "SELECT seg_id, engine, translation FROM calls WHERE error IS NULL LIMIT 10"')
    store.close()


if __name__ == '__main__':
    main()
