#!/usr/bin/env python
"""
Step 3: target transmission, which seeds cross into Chinese news and into which articles (model.md; src/crossings.py).
    -step embed_zh     a worker: every Chinese AI page of the crawls (as in step 1), its LaBSE vector, date and the
                       start of its text -> data/interim/step3/zh/<domain>__<part>.parquet
    -step screenshots  the English screenshots in Chinese articles (data/processed/english_screenshot_links.tsv)
                       matched against the seeds' texts -> data/interim/step3/screenshots.parquet
    -step candidates   a worker, one seed at a time: Chinese pages from 3 days before to 60 days after it appeared,
                       the TOP_K most similar to it (LaBSE), each scored sentence by sentence (best match, sentences
                       translated) -> data/interim/step3/candidates/<seed_id>.parquet
    -step table        every (seed, Chinese article) pair with any evidence: link and English quote (step 2),
                       screenshot, the candidates' similarities, the date gap -> data/interim/step3/pairs.parquet
    -step fit          model1 (src/model/model1.py) on the evidence: P(crossed) per pair
                       -> data/processed/seed_crossings.parquet, and per seed (crossed, Chinese articles and outlets,
                       first date and lag, evidence) -> data/processed/seed_transmission.tsv
Needs steps 1 and 2. Workers skip what is done. All of step 3: bash main/step3/go_step3.sh.

Run as a module from the repo root:
    python -m main.step3.crossings -step embed_zh -max-files 1          # test
    python -m main.step3.crossings -step fit
"""
import argparse
import csv
import datetime
import glob
import os
import random

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config.paths import (ENGLISH_SCREENSHOTS_PATH, PRIMARY_DB_PATH, SEED_CITATIONS_PATH, SEED_CROSSINGS_PATH,
                          SEED_QUOTES_PATH, SEED_TRANSMISSION_PATH, SEEDS_PATH, SITE_CRAWLS_DIR, STEP3_DIR)
from src.crossings import (FEATURES, LEAD_CHARS, MODEL, N_LEVELS, POSITIVE_HINT, TOP_K, WINDOW, feature_row,
                           seed_summary, sentence_scores)
from src.external_links import registered_domain
from src.file_worker import process_files
from src.model.model1 import fit, likelihood_ratios
from src.primary_sources import chinese_ai_page
from src.restatement.pages import chinese_sentences, english_sentences
from src.salience import days_between
from src.source_matching import SourceIndex
from src.source_texts import html_text
from src.warc_worker_cli import optional_int, setup_worker_process

ZH_SCHEMA = pa.schema([('url', pa.string()), ('outlet', pa.string()), ('date', pa.string()), ('title', pa.string()),
                       ('lead', pa.string()), ('vector', pa.list_(pa.float16()))])
CANDIDATE_SCHEMA = pa.schema([('seed_id', pa.string()), ('article', pa.string()), ('outlet', pa.string()),
                              ('date', pa.string()), ('doc_sim', pa.float32()), ('sent_sim', pa.float32()),
                              ('n_translated', pa.int32())])
MAX_SEED_SENTENCES = 80


def parse_args():
    parser = argparse.ArgumentParser(description='Step 3: which seeds cross into Chinese news')
    parser.add_argument('-step', required=True, choices=('embed_zh', 'screenshots', 'candidates', 'table', 'fit'))
    parser.add_argument('-seeds', default=str(SEEDS_PATH))
    parser.add_argument('-sources', default=str(PRIMARY_DB_PATH))
    parser.add_argument('-crawls-dir', default=str(SITE_CRAWLS_DIR))
    parser.add_argument('-screenshots', default=str(ENGLISH_SCREENSHOTS_PATH))
    parser.add_argument('-citations', default=str(SEED_CITATIONS_PATH), help='step 2')
    parser.add_argument('-quotes', default=str(SEED_QUOTES_PATH), help='step 2')
    parser.add_argument('-work-dir', default=str(STEP3_DIR))
    parser.add_argument('-out-crossings', default=str(SEED_CROSSINGS_PATH))
    parser.add_argument('-out-transmission', default=str(SEED_TRANSMISSION_PATH))
    parser.add_argument('-max-files', type=optional_int, default=None, help='workers: stop after N (testing)')
    return parser.parse_args()


def model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL, device='cpu')


def embed(m, texts):
    return m.encode(list(texts), normalize_embeddings=True, batch_size=32, convert_to_numpy=True)


def read_seeds(args):
    with open(args.seeds, encoding='utf-8', newline='') as f:
        seeds = list(csv.DictReader(f, delimiter='\t'))
    store = pd.read_parquet(args.sources, columns=['key', 'status', 'title', 'text'])
    store = store[store.status == 200].set_index('key')
    for s in seeds:
        s['text'] = store.text.get(s['key'], '') or ''
        s['title'] = store.title.get(s['key'], '') or s.get('title', '')
    return seeds


def zh_dir(args):
    return os.path.join(args.work_dir, 'zh')


def read_zh(args, columns):
    return pq.ParquetDataset(zh_dir(args)).read(columns=columns).to_pandas()


def embed_zh_step(args):
    os.makedirs(zh_dir(args), exist_ok=True)
    paths = glob.glob(os.path.join(args.crawls_dir, '*', 'html', '*.parquet'))
    random.shuffle(paths)
    last_day = datetime.date.today().isoformat()
    m = model()

    def name(path):
        return os.path.basename(os.path.dirname(os.path.dirname(path))) + '__' + os.path.basename(path)

    def run(path, out):
        rows = []
        for batch in pq.ParquetFile(path).iter_batches(batch_size=200, columns=['url', 'language', 'html']):
            for row in batch.to_pylist():
                try:
                    page = chinese_ai_page(row, last_day)
                    if page:
                        title, text = html_text(page[0])
                        rows.append({'url': row['url'], 'outlet': registered_domain(row['url']), 'date': page[1],
                                     'title': title, 'lead': text[:LEAD_CHARS]})
                except Exception:   # one unparseable page shouldn't lose the file
                    continue
        vectors = embed(m, [f"{r['title']}\n{r['lead'][:600]}" for r in rows]) if rows else []
        for r, v in zip(rows, vectors):
            r['vector'] = v.astype(np.float16).tolist()
        pq.write_table(pa.Table.from_pylist(rows, ZH_SCHEMA), out + '.part')
        os.replace(out + '.part', out)
        return {'pages': len(rows)}
    process_files(paths, lambda p: os.path.join(zh_dir(args), name(p)), run, args.max_files)


def screenshots_step(args):
    seeds = [s for s in read_seeds(args) if s['text']]
    index = SourceIndex([{'url': s['seed_id'], 'title': s['title'], 'text': s['text']} for s in seeds])
    with open(args.screenshots, encoding='utf-8', newline='') as f:
        shots = list(csv.DictReader(f, delimiter='\t'))
    rows = []
    for shot in shots:
        for seed_id, shared in index.match(shot['ocr']):
            rows.append({'seed_id': seed_id, 'article': shot['page'], 'shared': shared,
                         'date': shot.get('date', ''), 'src': shot['src']})
    pd.DataFrame(rows, columns=['seed_id', 'article', 'shared', 'date', 'src']).to_parquet(
        os.path.join(args.work_dir, 'screenshots.parquet'))
    print(f'{len(shots)} screenshots against {len(seeds)} seeds with text -> {len(rows)} matches, '
          f'{len({r["seed_id"] for r in rows})} seeds')


def candidates_step(args):
    out_dir = os.path.join(args.work_dir, 'candidates')
    os.makedirs(out_dir, exist_ok=True)
    seeds = {s['seed_id']: s for s in read_seeds(args) if s['text'] and s['first_seen']}
    zh = read_zh(args, ['url', 'outlet', 'date', 'lead', 'vector'])
    vectors = np.vstack(zh.vector.to_numpy()).astype(np.float32)
    days = pd.to_datetime(zh.date, errors='coerce')
    m = model()
    sentence_cache = {}

    def zh_sentence_vectors(i):
        if i not in sentence_cache:
            sentences = chinese_sentences(zh.lead.iat[i])[:MAX_SEED_SENTENCES]
            sentence_cache[i] = embed(m, sentences) if sentences else np.zeros((0, vectors.shape[1]))
        return sentence_cache[i]

    def run(seed_id, out):
        seed = seeds[seed_id]
        start = pd.Timestamp(seed['first_seen'])
        window = np.where((days >= start + pd.Timedelta(days=WINDOW[0])) &
                          (days <= start + pd.Timedelta(days=WINDOW[1])))[0]
        seed_vec = embed(m, [f"{seed['title']}\n{seed['text'][:600]}"])[0]
        seed_sentences = english_sentences(seed['text'])[:MAX_SEED_SENTENCES]
        seed_sent_vecs = embed(m, seed_sentences) if seed_sentences else np.zeros((0, len(seed_vec)))
        rows = []
        if len(window):
            sims = vectors[window] @ seed_vec
            for j in np.argsort(-sims)[:TOP_K]:
                i = window[j]
                best, n_translated = sentence_scores(seed_sent_vecs, zh_sentence_vectors(i))
                rows.append({'seed_id': seed_id, 'article': zh.url.iat[i], 'outlet': zh.outlet.iat[i],
                             'date': zh.date.iat[i], 'doc_sim': float(sims[j]), 'sent_sim': best,
                             'n_translated': n_translated})
        pq.write_table(pa.Table.from_pylist(rows, CANDIDATE_SCHEMA), out + '.part')
        os.replace(out + '.part', out)
        return {'window': len(window), 'best_sent': max((r['sent_sim'] or 0 for r in rows), default=0)}
    ids = list(seeds)
    random.shuffle(ids)
    process_files(ids, lambda s: os.path.join(out_dir, s + '.parquet'), run, args.max_files)


def table_step(args):
    """Every (seed, Chinese article) pair with evidence, one row each, with all its evidence."""
    seeds = {s['seed_id']: s for s in read_seeds(args)}
    pairs = {}

    def pair(seed_id, article):
        return pairs.setdefault((seed_id, article), {
            'seed_id': seed_id, 'article': article, 'outlet': registered_domain(article), 'date': '',
            'link': 0, 'screenshot': 0, 'en_quote': 0, 'doc_sim': None, 'sent_sim': None, 'n_translated': 0})
    cites = pd.read_parquet(args.citations, columns=['seed_id', 'language', 'article', 'date'])
    for r in cites[cites.language == 'zh'].itertuples():
        p = pair(r.seed_id, r.article)
        p.update(link=1, date=p['date'] or r.date)
    quotes = pd.read_parquet(args.quotes, columns=['seed_id', 'language', 'article'])
    for r in quotes[quotes.language == 'zh'].drop_duplicates(['seed_id', 'article']).itertuples():
        pair(r.seed_id, r.article)['en_quote'] = 1
    shots_path = os.path.join(args.work_dir, 'screenshots.parquet')
    if os.path.exists(shots_path):
        for r in pd.read_parquet(shots_path).itertuples():
            p = pair(r.seed_id, r.article)
            p.update(screenshot=1, date=p['date'] or r.date)
    for path in glob.glob(os.path.join(args.work_dir, 'candidates', '*.parquet')):
        for r in pq.read_table(path).to_pylist():
            p = pair(r['seed_id'], r['article'])
            p.update(doc_sim=r['doc_sim'], sent_sim=r['sent_sim'], n_translated=r['n_translated'],
                     date=p['date'] or r['date'])
    zh_dates = dict(read_zh(args, ['url', 'date']).itertuples(index=False))
    rows = []
    for p in pairs.values():
        p['date'] = p['date'] or zh_dates.get(p['article'], '')
        seed = seeds.get(p['seed_id'])
        p['date_gap'] = days_between(seed['first_seen'], p['date']) if seed and seed['first_seen'] and p['date'] \
            else None
        rows.append(p)
    df = pd.DataFrame(rows)
    df.to_parquet(os.path.join(args.work_dir, 'pairs.parquet'))
    print(f'{len(df)} (seed, Chinese article) pairs with evidence, {df.seed_id.nunique()} seeds: '
          f'link {int(df.link.sum())}, screenshot {int(df.screenshot.sum())}, English quote {int(df.en_quote.sum())}, '
          f'similarity scored {int(df.doc_sim.notna().sum())}')


def fit_step(args):
    seeds = {s['seed_id']: s for s in read_seeds(args)}
    df = pd.read_parquet(os.path.join(args.work_dir, 'pairs.parquet'))
    rows = df.to_dict('records')
    for r in rows:   # pandas NaN -> None for the binning
        for k in ('doc_sim', 'sent_sim', 'date_gap'):
            r[k] = None if isinstance(r[k], float) and r[k] != r[k] else r[k]
    X = np.array([feature_row(r) for r in rows], dtype=int).reshape(len(rows), len(FEATURES))
    params, r, history = fit(X, np.full(len(rows), np.nan), N_LEVELS, positive_hint=POSITIVE_HINT)
    df['p_crossed'] = r
    df.to_parquet(args.out_crossings)
    print(f'model1 on {len(rows)} pairs: pi = {params.pi:.4f}, {len(history)} EM iterations; '
          f'{int((r >= 0.5).sum())} pairs with P(crossed) >= 0.5')
    print('how much each level says about crossing (p(level | crossed) / p(level | not)):')
    for name, ratios in zip(FEATURES, likelihood_ratios(params)):
        print(f'  {name:11}', ' '.join(f'{x:8.2f}' for x in ratios))
    by_seed = {}
    for p in df.to_dict('records'):
        by_seed.setdefault(p['seed_id'], []).append(p)
    summary = [seed_summary(seeds[s], ps) for s, ps in by_seed.items() if s in seeds]
    summary += [seed_summary(seed, []) for s, seed in seeds.items() if s not in by_seed]
    summary.sort(key=lambda s: (-s['zh_outlets'], -s['max_p']))
    pd.DataFrame(summary).to_csv(args.out_transmission, sep='\t', index=False)
    crossed = [s for s in summary if s['crossed']]
    lags = sorted(s['lag_days'] for s in crossed if s['lag_days'] != '')
    print(f'{len(summary)} seeds -> {args.out_transmission}: {len(crossed)} crossed into Chinese news; '
          f'median lag {lags[len(lags) // 2] if lags else "-"} days')
    for s in summary[:15]:
        print(f"  {s['zh_outlets']:4d} outlets  link {s['by_link']:3d} shot {s['by_screenshot']:3d} "
              f"quote {s['by_en_quote']:3d} transl {s['translated']:3d}  {s['url'][:70]}")


def main():
    setup_worker_process()
    args = parse_args()
    os.makedirs(args.work_dir, exist_ok=True)
    {'embed_zh': embed_zh_step, 'screenshots': screenshots_step, 'candidates': candidates_step,
     'table': table_step, 'fit': fit_step}[args.step](args)


if __name__ == '__main__':
    main()
