#!/usr/bin/env python
"""
Where a phrase in a Fightin' Words result comes from: the documents of a run that contain it (the counted text:
w<N>/windows.parquet for a window run, docs.parquet for a whole-document run), by language, with their outlets,
their most common titles (a title repeated across outlets: syndication) and snippets in context. Chinese texts are
searched after the known renderings, as they were counted (文心一言 -> ERNIE Bot).

Run as a module from the repo root, on a pulled run folder (bash /tmp/pull.sh):
    python -m scripts.fightin_context -dir /tmp/fightin/safety_broad_1k/w200 -phrase "blackberry qnx"
    python -m scripts.fightin_context -dir /tmp/fightin/nvidia_1k/w200 -phrase 数据中心 -n 10
"""
import argparse
import os

import pandas as pd

from config.paths import FIGHTIN_RENDERINGS_PATH
from src.fightin.contexts import snippet, unit_regex
from src.fightin.renderings import KnownRenderings


def parse_args():
    parser = argparse.ArgumentParser(description='Documents and contexts of a phrase in a fightin run')
    parser.add_argument('-dir', required=True, help='a run folder: <experiment>/ or <experiment>/w<N>/')
    parser.add_argument('-phrase', required=True, help='as in the results (lowercase English, or Chinese)')
    parser.add_argument('-n', type=int, default=5, help='snippets per language')
    return parser.parse_args()


def read_texts(folder):
    """(lang, url, outlet, title, text) of the counted documents of a run folder."""
    if os.path.exists(os.path.join(folder, 'windows.parquet')):
        docs = pd.read_parquet(os.path.join(folder, 'windows.parquet'))
        return docs.rename(columns={'excerpt': 'text'})
    if os.path.exists(os.path.join(folder, 'docs.parquet')):
        return pd.read_parquet(os.path.join(folder, 'docs.parquet'))
    raise SystemExit(f'{folder}: no windows.parquet or docs.parquet (pull.sh skips docs.parquet; copy it, or use a '
                     'window run)')


def main():
    args = parse_args()
    docs = read_texts(args.dir)
    renderings = KnownRenderings.read(FIGHTIN_RENDERINGS_PATH)
    for lang in ('en', 'zh'):
        group = docs[docs['lang'] == lang]
        texts = group['text'].map(renderings.apply) if lang == 'zh' else group['text']
        regex = unit_regex(args.phrase, lang)
        found = group[texts.map(lambda t: bool(regex.search(t)))]
        print(f'\n=== {lang}: {len(found)} of {len(group)} documents, {found["outlet"].nunique()} outlets')
        if found.empty:
            continue
        print('outlets:', ', '.join(f'{o} {n}' for o, n in found['outlet'].value_counts().head(8).items()))
        print('titles:')
        for title, n in found['title'].str[:100].value_counts().head(5).items():
            print(f'  {n:4d}  {title}')
        for row in found.drop_duplicates('outlet').head(args.n).itertuples():
            print(f'- {row.outlet}  {row.url}\n    {snippet(texts[row.Index], regex)}')


if __name__ == '__main__':
    main()
