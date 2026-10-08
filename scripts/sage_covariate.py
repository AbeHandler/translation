#!/usr/bin/env python
"""
SAGE (src/sage) with document covariates: which terms each covariate value shifts, against the background of the
whole document set, each facet absorbing its own vocabulary (e.g. outlet house style stays out of the Nvidia
component). Input: a document table (parquet: lang, outlet, title, text, and any covariate columns), e.g. a fightin
sample (results/fightin/<experiment>/docs.parquet) or window excerpts (w<N>/windows.parquet).
    covariates   columns of the table, or made here from a regex on title + text: -covariate nvidia='Nvidia|英伟达'
                 gives nvidia = yes / no
    facets       the covariates modelled (-facets nvidia,outlet), each one sparse component per value
    interactions pairs of facets whose combination gets its own component (-interactions lang:nvidia)
Output in results/sage_covariate/<experiment>/: components.tsv (facet, level, term, eta, count: one row per
non-zero deviation, count = the term's uses in the level's documents), summary.txt.

Run as a module from the repo root:
    python -m scripts.sage_covariate -docs /tmp/fightin/all_5k/docs.parquet -lang en \\
        -covariate nvidia='Nvidia' -facets nvidia,outlet -experiment-name en_nvidia
"""
import argparse
import os
import re

import numpy as np
import pandas as pd
import torch

from config.paths import FIGHTIN_RENDERINGS_PATH, REPO_ROOT, STOPWORDS_EN_PATH
from src.fightin.concepts import read_stopwords
from src.fightin.renderings import KnownRenderings
from src.fightin.units import parse_ns
from src.sage.featurise import featurise
from src.sage.models import AdditiveSAGE, ZERO, sparsity

NAME = 'sage_covariate'


def parse_args():
    parser = argparse.ArgumentParser(description='SAGE with document covariates')
    parser.add_argument('-docs', required=True, help='a parquet of documents: lang, outlet, title, text, ...')
    parser.add_argument('-lang', default=None, choices=('en', 'zh'), help='only this language (default: all)')
    parser.add_argument('-covariate', action='append', default=[],
                        help="name='regex': a yes/no covariate, the regex found in title or text (case-insensitive)")
    parser.add_argument('-facets', required=True, help='comma-separated covariate columns to model')
    parser.add_argument('-interactions', default='', help='comma-separated pairs a:b, each a facet of its own')
    parser.add_argument('-ngrams', default='2-3', help="units: '2-3' phrases (default), 1 words")
    parser.add_argument('-min-df', type=int, default=5)
    parser.add_argument('-max-vocab', type=int, default=30000)
    parser.add_argument('-prior', default='jeffreys', choices=('jeffreys', 'exponential'))
    parser.add_argument('-top', type=int, default=30, help='terms printed per component')
    parser.add_argument('-experiment-name', required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    out = os.path.join(REPO_ROOT, 'results', NAME, args.experiment_name)
    os.makedirs(out, exist_ok=True)
    docs = pd.read_parquet(args.docs)
    if 'excerpt' in docs:                       # a fightin window run's windows.parquet
        docs = docs.rename(columns={'excerpt': 'text'})
    if args.lang:
        docs = docs[docs['lang'] == args.lang]
    for spec in args.covariate:
        name, _, pattern = spec.partition('=')
        regex = re.compile(pattern, re.I)
        docs[name] = (docs['title'].fillna('') + '\n' + docs['text'].fillna('')).map(
            lambda t: 'yes' if regex.search(t) else 'no')
    facets = [f for f in args.facets.split(',') if f]
    for pair in filter(None, args.interactions.split(',')):
        a, b = pair.split(':')
        docs[f'{a}x{b}'] = docs[a].astype(str) + '·' + docs[b].astype(str)
        facets.append(f'{a}x{b}')
    for f in facets:
        print(f'{f}:', docs[f].value_counts().head(10).to_dict())

    X, vocab, docs = featurise(docs, parse_ns(args.ngrams), args.min_df, args.max_vocab,
                               renderings=KnownRenderings.read(FIGHTIN_RENDERINGS_PATH),
                               stop=read_stopwords(STOPWORDS_EN_PATH))
    print(f'{X.shape[0]} documents, {len(vocab)} terms; fitting SAGE ({args.prior}) on facets {facets}', flush=True)
    model = AdditiveSAGE(prior=args.prior).fit(X, {f: docs[f].to_numpy() for f in facets})

    rows, summary = [], []
    for f in facets:
        summary.append(f'{f}: sparsity {sparsity(model.eta[f]):.1%}')
        for k, level in enumerate(model.levels[f]):
            eta = model.eta[f][k]
            level_counts = np.asarray(X[(docs[f] == level).to_numpy()].sum(0)).ravel()
            for i in torch.nonzero(eta.abs() >= ZERO).ravel().tolist():
                rows.append({'facet': f, 'level': level, 'term': vocab[i], 'eta': round(float(eta[i]), 4),
                             'count': int(level_counts[i])})
    table = pd.DataFrame(rows).sort_values(['facet', 'level', 'eta'], ascending=[True, True, False])
    table.to_csv(os.path.join(out, 'components.tsv'), sep='\t', index=False)
    with open(os.path.join(out, 'summary.txt'), 'w') as fh:
        fh.write('\n'.join(summary) + '\n')
    print('\n'.join(summary))
    for f in facets:
        if f == 'outlet':
            continue                        # dozens of levels: see components.tsv
        for level, group in table[table['facet'] == f].groupby('level'):
            top = group.head(args.top)
            print(f'\n=== {f} = {level}: {len(group)} non-zero terms; top {len(top)}:')
            print(', '.join(f"{t} ({e:+.2f}, {c})" for t, e, c in zip(top['term'], top['eta'], top['count'])))
    print(f"\n-> {os.path.join(out, 'components.tsv')}")


if __name__ == '__main__':
    main()
