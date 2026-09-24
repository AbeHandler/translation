#!/usr/bin/env python
"""
The MT pipeline, in steps (-step, default all), for the source documents in config/mt_sources.yaml:
    fetch      download each source with a url -> data/raw/mt_sources/<id>.html (raw) and <id>.txt (its text,
               parsed the source's own way: its selector, or newspaper4k). Skips sources already fetched.
    queue      split each source's text into segments (sentences, with their neighbours as context) and add
               them to the MT queue in data/processed/translations.sqlite. Skips segments already queued.
    translate  the runner: translate every queued segment with every registered engine, skipping calls
               already stored (src/translation/runner.py; the store's docstring has the tables)

Every step is safe to stop (Ctrl-C, scancel) and rerun: nothing done is redone, nothing paid for is paid for
twice. Add a document by adding it to config/mt_sources.yaml and rerunning. Only one runner can use a
database at a time. Calls run in random order.

API keys come from environment variables (src/translation/backends.py), loaded from the repo's .env file
(one KEY=value per line; gitignored) unless already set. A missing one stops the translate step before any
call. -engines limits it to some engines.

Run as a module from the repo root:
    python -m scripts.run_translations -dry-run                   # fetch, queue, then show calls left
    python -m scripts.run_translations -engines grok deepseek
    python -m scripts.run_translations -step fetch
"""
import argparse
import logging
import os
from collections import Counter

from dotenv import load_dotenv

from config.paths import ENV_PATH, MT_SOURCES_CONFIG, MT_SOURCES_DIR, TRANSLATIONS_DB
from src.translation.backends import ENGINES, build_engines
from src.translation.runner import plan_calls, run_queue, runner_lock
from src.translation.segments import CONTEXT_MODES
from src.translation.sources import extract_text, fetch_html, read_sources, segments
from src.translation.store import TranslationStore
from src.warc_worker_cli import setup_worker_process

STEPS = ('fetch', 'queue', 'translate')


def parse_args():
    parser = argparse.ArgumentParser(description='Fetch, queue and translate the MT source documents')
    parser.add_argument('-step', default='all', choices=STEPS + ('all',))
    parser.add_argument('-sources', default=str(MT_SOURCES_CONFIG))
    parser.add_argument('-sources-dir', default=str(MT_SOURCES_DIR), help='fetched <id>.html and <id>.txt')
    parser.add_argument('-db', default=str(TRANSLATIONS_DB))
    parser.add_argument('-engines', nargs='+', default=sorted(ENGINES), choices=sorted(ENGINES),
                        help='default: every registered engine')
    parser.add_argument('-context-modes', nargs='+', default=list(CONTEXT_MODES), choices=CONTEXT_MODES)
    parser.add_argument('-n-samples', type=int, default=5, help='samples per LLM engine; NMT engines run once')
    parser.add_argument('-temperature', type=float, default=0.7, help='LLM temperature; 0 collapses the samples')
    parser.add_argument('-delay', type=float, default=0.4, help='seconds between calls')
    parser.add_argument('-dry-run', action='store_true', help='translate step: print the calls left, per engine')
    return parser.parse_args()


def fetch(sources, sources_dir):
    """Save each url source's raw HTML, then its text. Raw first, so a parse can be redone without refetching."""
    os.makedirs(sources_dir, exist_ok=True)
    for source in sources:
        html_path, text_path = (os.path.join(sources_dir, f'{source.id}.{ext}') for ext in ('html', 'txt'))
        if not source.url or os.path.exists(text_path):
            continue
        if not os.path.exists(html_path):
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(fetch_html(source.url))
        with open(html_path, encoding='utf-8') as f:
            text = extract_text(f.read(), source.url, source.selector)
        if not text.strip():
            raise ValueError(f'source {source.id}: no text found at {source.url}; give it a selector')
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(text + '\n')
        logging.info('fetched %s: %d words -> %s', source.id, len(text.split()), text_path)


def queue(sources, sources_dir, store, sources_path):
    for source in sources:
        text = source.text
        if source.url:
            text_path = os.path.join(sources_dir, f'{source.id}.txt')
            if not os.path.exists(text_path):
                raise FileNotFoundError(f'source {source.id} has not been fetched; run -step fetch')
            with open(text_path, encoding='utf-8') as f:
                text = f.read()
        added, already = store.enqueue(segments(source, text), f'{os.path.basename(sources_path)}:{source.id}')
        logging.info('queued %s: %d segments added, %d already queued', source.id, added, already)


def translate(store, args):
    engines = build_engines(args.engines)
    if args.dry_run:
        print_todo(store, engines, args)
        return
    with runner_lock(args.db + '.lock'):
        run_id, counts = run_queue(store, engines, args.context_modes, args.n_samples, args.temperature,
                                   args.delay, settings=vars(args))
    print(f'\nrun {run_id}: {counts} -> {args.db}')
    print('\nSpot checks:')
    print(f'  sqlite3 {args.db} "SELECT engine, model, context_mode, COUNT(*), SUM(error IS NOT NULL) '
          'FROM calls GROUP BY 1, 2, 3"')
    print(f'  sqlite3 {args.db} "SELECT seg_id, engine, translation FROM calls WHERE error IS NULL LIMIT 10"')


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
    load_dotenv(ENV_PATH)  # API keys; variables already set in the environment win
    steps = STEPS if args.step == 'all' else (args.step,)
    sources = read_sources(args.sources)
    store = TranslationStore(args.db)
    if 'fetch' in steps:
        fetch(sources, args.sources_dir)
    if 'queue' in steps:
        queue(sources, args.sources_dir, store, args.sources)
    if 'translate' in steps:
        translate(store, args)
    store.close()


if __name__ == '__main__':
    main()
