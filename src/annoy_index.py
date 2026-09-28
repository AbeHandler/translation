"""
One Annoy index over page embeddings (the files src/embed_html.py writes). Logic only: no paths.

build_annoy_index() reads every embeddings file, adds each non-null embedding under an integer id, builds the
trees, and writes to out_dir, replacing what is there:
    index.ann       the Annoy index (metric 'angular': the vectors are normalized, so this ranks by cosine)
    ids.parquet     id -> record_id, url, domain, language, to look up what a query returns
    info.json       model, dimensions, counts, n_trees, build time
Each is written under a .part name and renamed only once all three are complete. Annoy indexes can't be
added to, so this always rebuilds from every file; rerun it to take in new embeddings.
"""
import datetime
import json
import logging
import os
import time

import pyarrow as pa
import pyarrow.parquet as pq
from annoy import AnnoyIndex

IDS_SCHEMA = pa.schema([
    ('id', pa.int64()),
    ('record_id', pa.string()),
    ('url', pa.string()),
    ('domain', pa.string()),
    ('language', pa.string()),
])
OUTPUTS = ('index.ann', 'ids.parquet', 'info.json')
LOG_EVERY_FILES = 100

logger = logging.getLogger(__name__)


def build_annoy_index(embedding_files, out_dir, n_trees=50, n_jobs=-1):
    """embedding_files: (domain, path) pairs. Returns the info written to info.json."""
    os.makedirs(out_dir, exist_ok=True)
    part = {name: os.path.join(out_dir, name + '.part') for name in OUTPUTS}
    index, model, ids = None, None, []
    started = time.time()
    for n, (domain, path) in enumerate(embedding_files, 1):
        table = pq.read_table(path)
        file_model = table.schema.metadata[b'model'].decode()
        model = model or file_model
        if file_model != model:
            raise ValueError(f'{path} was embedded with {file_model}, others with {model}; one index needs one model')
        for row in table.select(['record_id', 'url', 'language', 'embedding']).to_pylist():
            if row['embedding'] is None:  # no text on the page
                continue
            if index is None:
                index = AnnoyIndex(len(row['embedding']), 'angular')
                index.on_disk_build(part['index.ann'])  # built in the file, not in RAM
            index.add_item(len(ids), row['embedding'])
            ids.append({'id': len(ids), 'record_id': row['record_id'], 'url': row['url'], 'domain': domain,
                        'language': row['language']})
        if n % LOG_EVERY_FILES == 0 or n == len(embedding_files):
            logger.info('read %d/%d embeddings files, %d vectors added (%.0fs)', n, len(embedding_files), len(ids),
                        time.time() - started)
    if index is None:
        raise ValueError('no embeddings to index')
    logger.info('building %d trees over %d vectors (the slow part; no progress until it ends)...', n_trees, len(ids))
    build_started = time.time()
    index.build(n_trees, n_jobs=n_jobs)
    logger.info('built in %.0fs; writing ids and info', time.time() - build_started)
    info = {'model': model, 'dimensions': index.f, 'items': len(ids), 'embedding_files': len(embedding_files),
            'domains': len({row['domain'] for row in ids}), 'n_trees': n_trees,
            'built_at': datetime.datetime.now().isoformat()}
    index.unload()
    pq.write_table(pa.Table.from_pylist(ids, IDS_SCHEMA), part['ids.parquet'], compression='zstd')
    with open(part['info.json'], 'w') as f:
        json.dump(info, f, indent=2)
    for name in OUTPUTS:
        os.replace(part[name], os.path.join(out_dir, name))
    return info


def load_annoy_index(out_dir):
    """(AnnoyIndex memory-mapped from out_dir, ids table, info)."""
    with open(os.path.join(out_dir, 'info.json')) as f:
        info = json.load(f)
    index = AnnoyIndex(info['dimensions'], 'angular')
    index.load(os.path.join(out_dir, 'index.ann'))
    return index, pq.read_table(os.path.join(out_dir, 'ids.parquet')), info
