"""
A worker over the WARC list: WARCs in random order, each done at most once across all workers. A WARC is done
when <out_dir>/<name>.ai.warc.gz exists, or its <name>.links.jsonl does (the cleanup step deletes the AI WARC
once its links are out, to save space); a worker claims one with a .lock next to it (src/file_worker.py), so
workers never stream the same WARC. Existence is checked as the worker goes, not up front, since the list has
millions of entries. A WARC that fails (network, throttling) is logged and left for later; too many failures in
a row stop the worker.
"""
import logging
import os
import random

from src.file_worker import claim_lock

logger = logging.getLogger(__name__)
MAX_FAILURES_IN_A_ROW = 10


def out_path(out_dir, path):
    """crawl-data/.../CC-MAIN-2026...-00000.warc.gz -> <out_dir>/CC-MAIN-2026...-00000.ai.warc.gz"""
    return os.path.join(out_dir, os.path.basename(path).removesuffix('.warc.gz') + '.ai.warc.gz')


def links_path(ai_warc_path):
    """<name>.ai.warc.gz -> <name>.links.jsonl (its pages' links, src/common_crawl_full/links.py)"""
    return ai_warc_path.removesuffix('.ai.warc.gz') + '.links.jsonl'


def is_done(out):
    return os.path.exists(out) or os.path.exists(links_path(out))


def process_warcs(list_path, out_dir, process, max_warcs=None, seed=None):
    """Run process(warc path, out path) -> counts on WARCs from list_path in random order. Returns WARCs done."""
    with open(list_path) as f:
        paths = [line.strip() for line in f if line.strip()]
    random.Random(seed).shuffle(paths)
    os.makedirs(out_dir, exist_ok=True)
    logger.info('%d WARCs in %s', len(paths), list_path)
    n_done = failures = 0
    for path in paths:
        out = out_path(out_dir, path)
        if is_done(out) or not claim_lock(out + '.lock'):
            continue
        try:
            counts = process(path, out)
            logger.info('done %s %s', os.path.basename(out), counts)
            n_done, failures = n_done + 1, 0
        except Exception as exc:
            failures += 1
            logger.error('failed %s: %s: %s', path, type(exc).__name__, exc)
            if os.path.exists(out + '.part'):
                os.remove(out + '.part')
            if failures >= MAX_FAILURES_IN_A_ROW:
                raise RuntimeError(f'{failures} WARCs failed in a row; stopping') from exc
        finally:
            os.remove(out + '.lock')
        if max_warcs and n_done >= max_warcs:
            break
    return n_done
