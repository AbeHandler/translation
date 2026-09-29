#!/usr/bin/env python
"""
AI articles on Wikipedia and the external links they cite, per language (-lang), in steps (-step):
    download  the multistream dump and its index -> $TMP/wikipedia_dumps/
    pages     every article (main namespace, not a redirect) whose wikitext says "AI" as a word, from one chunk
              of the dump at a time -> data/interim/wikipedia/<lang>/pages/chunk_NNNNN.parquet. A worker step:
              scripts/go_wikipedia.sh runs many; they share the chunks through .lock files. The one full pass.
    filter    the AI articles: config/wikipedia.yaml's rule over those pages -> .../<lang>/ai_pages.parquet
              (rebuilt every run: change the rule, rerun filter and queue)
    queue     their external links, shuffled, 1000 per shard -> $TMP/wikipedia_queue/<lang>/shard_*.jsonl
              ({srcpage, url}), for scripts/process_queue.sh (src/shard_queue). Adds only links not queued yet,
              so results already made stay valid; delete the queue dir for a fresh start.
Every step skips work already done; filter always rebuilds (it's cheap).

Run as a module from the repo root:
    python -m scripts.wikipedia_pipeline -lang zh -step download
    python -m scripts.wikipedia_pipeline -lang zh -step pages -max-chunks 1      # test: one chunk
"""
import argparse
import glob
import json
import os

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from config.paths import WIKIPEDIA_CONFIG, WIKIPEDIA_DIR, wikipedia_tmp_dir
from src.file_worker import process_files
from src.shard_queue.shards import add_to_queue
from src.warc_worker_cli import optional_int, setup_worker_process
from src.wikipedia.dump import chunks, download, dump_paths, read_pages, stream_offsets
from src.ai_mentions import mentions_ai
from src.wikipedia.links import external_links

STEPS = ('download', 'pages', 'filter', 'queue')
PAGES_SCHEMA = pa.schema([('page_id', pa.int64()), ('title', pa.string()), ('ai_mentions', pa.int32()),
                          ('text', pa.string())])


def parse_args():
    parser = argparse.ArgumentParser(description='AI articles on Wikipedia and their external links')
    parser.add_argument('-lang', required=True, help='wikipedia language code, e.g. zh or en')
    parser.add_argument('-step', required=True, choices=STEPS)
    parser.add_argument('-config', default=str(WIKIPEDIA_CONFIG))
    parser.add_argument('-dump-dir', default='', help='default $TMP/wikipedia_dumps')
    parser.add_argument('-queue-dir', default='', help='default $TMP/wikipedia_queue/<lang>')
    parser.add_argument('-max-chunks', type=optional_int, default=None, help='pages: stop after N chunks (testing)')
    return parser.parse_args()


def chunk_list(dump_dir, lang, streams_per_chunk):
    """The dump's chunks as [(start, end)], computed from the index once and cached next to the dump."""
    dump, index = dump_paths(dump_dir, lang)
    cache = f'{dump}.chunks{streams_per_chunk}.json'
    if not os.path.exists(cache):
        byte_ranges = chunks(stream_offsets(index), os.path.getsize(dump), streams_per_chunk)
        with open(cache + f'.{os.getpid()}.part', 'w') as f:
            json.dump(byte_ranges, f)
        os.replace(cache + f'.{os.getpid()}.part', cache)
    with open(cache) as f:
        return json.load(f)


def pages(args, config, dump_dir, lang_dir):
    dump, _ = dump_paths(dump_dir, args.lang)
    if not os.path.exists(dump):
        raise FileNotFoundError(f'no dump at {dump}; run -step download first')
    byte_ranges = chunk_list(dump_dir, args.lang, config['streams_per_chunk'])
    out_dir = os.path.join(lang_dir, 'pages')
    names = [f'chunk_{n:05d}' for n in range(len(byte_ranges))]

    def write_chunk(name, out_path):
        start, end = byte_ranges[int(name.split('_')[1])]
        rows, n_pages = [], 0
        for page in read_pages(dump, start, end):
            n_pages += 1
            n_ai = mentions_ai(page.text) if page.ns == 0 and not page.redirect else 0
            if n_ai:
                rows.append({'page_id': page.page_id, 'title': page.title, 'ai_mentions': n_ai, 'text': page.text})
        pq.write_table(pa.Table.from_pylist(rows, PAGES_SCHEMA), out_path + '.part', compression='zstd')
        os.rename(out_path + '.part', out_path)
        return {'pages': n_pages, 'say_ai': len(rows)}

    process_files(names, lambda name: os.path.join(out_dir, name + '.parquet'), write_chunk,
                  max_files=args.max_chunks)
    print(f'{len(glob.glob(os.path.join(out_dir, "chunk_*.parquet")))} of {len(names)} chunks done -> {out_dir}')


def filter_pages(args, config, dump_dir, lang_dir):
    """Refuses until every chunk has its pages (unless -max-chunks, for tests), so the AI set is the whole dump."""
    paths = sorted(glob.glob(os.path.join(lang_dir, 'pages', 'chunk_*.parquet')))
    n_chunks = len(chunk_list(dump_dir, args.lang, config['streams_per_chunk']))
    if len(paths) < n_chunks and not args.max_chunks:
        raise FileNotFoundError(f'only {len(paths)} of {n_chunks} chunks have pages; rerun -step pages first')
    rule = config['filter']
    table = pa.concat_tables(pq.read_table(p, schema=PAGES_SCHEMA) for p in paths)
    kept = table.filter(pa.compute.greater_equal(table['ai_mentions'], rule['min_ai_mentions']))
    out = os.path.join(lang_dir, 'ai_pages.parquet')
    pq.write_table(kept, out + '.part', compression='zstd')
    os.rename(out + '.part', out)
    print(f'{kept.num_rows} of {table.num_rows} pages saying "AI" pass {rule} ({len(paths)} chunks) -> {out}')
    print('Spot check:\n  python -c "import pyarrow.parquet as pq, random; t = pq.read_table(\'' + out +
          '\', columns=[\'title\', \'ai_mentions\']).to_pylist(); print(random.sample(t, 20))"')


def queue(args, config, lang_dir, queue_dir):
    ai_pages = os.path.join(lang_dir, 'ai_pages.parquet')
    if not os.path.exists(ai_pages):
        raise FileNotFoundError(f'no {ai_pages}; run -step filter first')
    rows = [{'srcpage': page['title'], 'url': url}
            for page in pq.read_table(ai_pages, columns=['title', 'text']).to_pylist()
            for url in external_links(page['text'])]
    added, already = add_to_queue(rows, queue_dir, config['queue']['shard_size'])
    print(f'{len(rows)} links from AI articles: {added} new ones queued ({already} were already) in {queue_dir}')
    print(f'Process them: bash scripts/process_queue.sh wikipedia_{args.lang}')


def main():
    setup_worker_process()
    args = parse_args()
    with open(args.config) as f:
        config = yaml.safe_load(f)
    dump_dir = args.dump_dir or str(wikipedia_tmp_dir('dumps'))
    lang_dir = os.path.join(str(WIKIPEDIA_DIR), args.lang)
    if args.step == 'download':
        download(args.lang, dump_dir)
    elif args.step == 'pages':
        pages(args, config, dump_dir, lang_dir)
    elif args.step == 'filter':
        filter_pages(args, config, dump_dir, lang_dir)
    else:
        queue(args, config, lang_dir, args.queue_dir or os.path.join(str(wikipedia_tmp_dir('queue')), args.lang))


if __name__ == '__main__':
    main()
