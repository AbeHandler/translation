#!/usr/bin/env python
"""
The MT runner: translates every segment in the MT queue with every registered engine (src/translation;
the store's docstring has the tables), all in data/processed/translations.sqlite.

Start it, stop it (Ctrl-C, scancel) and rerun it at will: calls already stored successfully are skipped, so
nothing is paid for twice, and new segments (scripts/enqueue_segments.py) or a new engine are picked up on
the next run. Calls run in random order. Only one runner can use a database at a time.

API keys come from environment variables (src/translation/backends.py); a missing one stops the runner
before any call. -engines limits it to some engines.

Run as a module from the repo root:
    python -m scripts.run_translations -dry-run      # what's left to do, per engine; calls nothing
    python -m scripts.run_translations
    python -m scripts.run_translations -engines google_nmt deepseek grok
"""
import argparse
from collections import Counter

from config.paths import TRANSLATIONS_DB
from src.translation.backends import ENGINES, build_engines
from src.translation.runner import plan_calls, run_queue, runner_lock
from src.translation.segments import CONTEXT_MODES
from src.translation.store import TranslationStore
from src.warc_worker_cli import setup_worker_process


def parse_args():
    parser = argparse.ArgumentParser(description='Translate the MT queue with every registered engine')
    parser.add_argument('-db', default=str(TRANSLATIONS_DB))
    parser.add_argument('-engines', nargs='+', default=sorted(ENGINES), choices=sorted(ENGINES),
                        help='default: every registered engine')
    parser.add_argument('-context-modes', nargs='+', default=list(CONTEXT_MODES), choices=CONTEXT_MODES)
    parser.add_argument('-n-samples', type=int, default=5, help='samples per LLM engine; NMT engines run once')
    parser.add_argument('-temperature', type=float, default=0.7, help='LLM temperature; 0 collapses the samples')
    parser.add_argument('-delay', type=float, default=0.4, help='seconds between calls')
    parser.add_argument('-dry-run', action='store_true', help='print the calls left to make, per engine')
    return parser.parse_args()


def print_todo(store, engines, args):
    """Calls left to make and their source characters, per engine (dry run)."""
    calls = plan_calls(store.queued_segments(), engines, args.context_modes, args.n_samples)
    done = store.succeeded_keys()
    todo = [call for call in calls if call.key not in done]
    n_calls, n_chars = Counter(), Counter()
    for call in todo:
        n_calls[f'{call.engine.name}/{call.engine.model}'] += 1
        n_chars[f'{call.engine.name}/{call.engine.model}'] += len(call.source_text)
    for engine, n in sorted(n_calls.items()):
        print(f'  {engine:32} {n:6} calls to make  {n_chars[engine]:9} source chars')
    print(f'  {len(todo)} of {len(calls)} planned calls left to make')


def main():
    setup_worker_process()  # logging; a clean exit on SIGTERM (scancel)
    args = parse_args()
    engines = build_engines(args.engines)
    store = TranslationStore(args.db)
    if args.dry_run:
        print_todo(store, engines, args)
        return
    with runner_lock(args.db + '.lock'):
        run_id, counts = run_queue(store, engines, args.context_modes, args.n_samples, args.temperature,
                                   args.delay, settings=vars(args))
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
