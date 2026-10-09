#!/usr/bin/env python
"""
SAGE topics (src/sage/topics.py) on a document table (a fightin sample's docs.parquet): K latent topics as sparse
deviations from the background, with document labels (e.g. language x Nvidia) as facets of their own, so that
topics are shared across labels and a label's own vocabulary (Chinese function phrases, house style) doesn't make
topics of its own. The labels' topic prevalence says which topics each label's coverage dwells on.
    one language   -lang en (or zh): its phrases as they are
    both           -mapping results/sage_crosslingual/<experiment>/mapping.tsv: Chinese phrases on English
                   concepts (scripts/sage_crosslingual.py made and cached it), so topics span both languages
    labels         -labels lang,nvidia: the combination of these columns per document (en·yes, zh·no ...);
                   columns made from a regex with -covariate nvidia='Nvidia|英伟达'
Output in results/sage_topics/<experiment>/: topics.tsv (topic, rank, term, eta, lift: the rise in the term's
probability over the background, the ranking: by eta alone rare exclusive phrases come first), labels.tsv,
prevalence.tsv (label x topic: mean topic proportions), doc_topics.parquet (url, lang, label, topic proportions).
Printed: each topic's top terms and its prevalence per label; with labels lang and a yes/no covariate, each
topic's covariate association per language (prevalence at yes minus at no) and their difference.

Run as a module from the repo root:
    python -m scripts.sage_topics -docs /tmp/fightin/all_5k/docs.parquet \\
        -mapping results/sage_crosslingual/nvidia/mapping.tsv -covariate nvidia='Nvidia|英伟达' \\
        -labels lang,nvidia -topics 30 -experiment-name nvidia
"""
import argparse
import os
import re

import numpy as np
import pandas as pd

from config.paths import FIGHTIN_RENDERINGS_PATH, REPO_ROOT, STOPWORDS_EN_PATH
from src.fightin.concepts import read_stopwords
from src.fightin.renderings import KnownRenderings
from src.fightin.units import parse_ns
from src.sage.crosslingual import to_concepts
from src.sage.featurise import count_matrix, doc_units, vocabulary
from src.sage.models import sparsity
from src.sage.topics import SAGETopics

NAME = 'sage_topics'


def parse_args():
    parser = argparse.ArgumentParser(description='SAGE topics with label facets')
    parser.add_argument('-docs', required=True)
    parser.add_argument('-lang', default=None, choices=('en', 'zh'), help='one language only')
    parser.add_argument('-mapping', default=None, help='Chinese unit -> English concept (both languages)')
    parser.add_argument('-threshold', type=float, default=0.7, help='with -mapping: the cosine for a mapping')
    parser.add_argument('-covariate', action='append', default=[], help="name='regex': a yes/no column")
    parser.add_argument('-labels', default='', help='comma-separated columns, combined into one label')
    parser.add_argument('-topics', type=int, default=30)
    parser.add_argument('-interactions', action='store_true', help='label x topic components (slower)')
    parser.add_argument('-em', type=int, default=60, help='EM iterations')
    parser.add_argument('-restarts', type=int, default=3)
    parser.add_argument('-ngrams', default='2-3')
    parser.add_argument('-min-df', type=int, default=10)
    parser.add_argument('-max-vocab', type=int, default=10000)
    parser.add_argument('-top', type=int, default=12, help='terms printed per topic')
    parser.add_argument('-experiment-name', required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.lang and not args.mapping:
        raise SystemExit('give -lang (one language) or -mapping (both, on shared concepts)')
    out = os.path.join(REPO_ROOT, 'results', NAME, args.experiment_name)
    os.makedirs(out, exist_ok=True)
    docs = pd.read_parquet(args.docs)
    if args.lang:
        docs = docs[docs['lang'] == args.lang]
    for spec in args.covariate:
        name, _, pattern = spec.partition('=')
        regex = re.compile(pattern, re.I)
        docs[name] = (docs['title'].fillna('') + '\n' + docs['text'].fillna('')).map(
            lambda t, r=regex: 'yes' if r.search(t) else 'no')
    stop = read_stopwords(STOPWORDS_EN_PATH)
    found, docs = doc_units(docs, parse_ns(args.ngrams), renderings=KnownRenderings.read(FIGHTIN_RENDERINGS_PATH),
                            stop=stop)
    if args.mapping:
        table = pd.read_csv(args.mapping, sep='\t', keep_default_na=False)
        mapping = {u: (c, s) if s >= args.threshold else (u, s)
                   for u, c, s in zip(table['unit'], table['concept'], table['cosine'])}
        found = to_concepts(found, docs['lang'].to_numpy(), mapping, stop)
    vocab = vocabulary(found, args.min_df, args.max_vocab)
    X = count_matrix(found, vocab)
    keep = np.asarray(X.sum(1)).ravel() > 0
    X, docs = X[keep], docs[keep].reset_index(drop=True)
    columns = [c for c in args.labels.split(',') if c]
    labels = docs[columns].astype(str).agg('·'.join, axis=1).to_numpy() if columns else None
    print(f'{X.shape[0]} documents, {len(vocab)} terms, {int(X.sum())} tokens; labels: '
          f'{pd.Series(labels).value_counts().to_dict() if labels is not None else "none"}', flush=True)

    model = SAGETopics(args.topics, em_iters=args.em, restarts=args.restarts, interactions=args.interactions,
                       say=lambda line: print(line, flush=True)).fit(X, labels)
    print(f'topics sparsity {sparsity(model.eta_topic):.1%}, labels {sparsity(model.eta_label):.1%}')

    rows = []
    background = np.exp(model.m.numpy())
    for k in range(args.topics):     # ranked by lift: how much the topic raises the term's probability over the
        eta = model.eta_topic[k].numpy()        # background (by eta alone, rare exclusive phrases come first)
        p = np.exp(model.m.numpy() + eta)
        lift = p / p.sum() - background
        order = np.argsort(-lift)[:50]
        rows += [{'topic': k, 'rank': r, 'term': vocab[i], 'eta': round(float(eta[i]), 4),
                  'lift': float(lift[i])} for r, i in enumerate(order) if eta[i] > 0]
    topics = pd.DataFrame(rows)
    topics.to_csv(os.path.join(out, 'topics.tsv'), sep='\t', index=False)
    label_rows = []
    for j, level in enumerate(model.levels):
        order = np.argsort(-model.eta_label[j].numpy())[:50]
        label_rows += [{'label': level, 'term': vocab[i], 'eta': round(float(model.eta_label[j, i]), 4)}
                       for i in order if model.eta_label[j, i] > 0]
    pd.DataFrame(label_rows).to_csv(os.path.join(out, 'labels.tsv'), sep='\t', index=False)
    prevalence = pd.DataFrame(model.prevalence(), index=model.levels,
                              columns=[f't{k}' for k in range(args.topics)])
    prevalence.round(4).to_csv(os.path.join(out, 'prevalence.tsv'), sep='\t')
    theta = pd.DataFrame(model.doc_topics(), columns=[f't{k}' for k in range(args.topics)])
    pd.concat([docs[['url', 'lang']].assign(label=labels if labels is not None else ''), theta], axis=1).to_parquet(
        os.path.join(out, 'doc_topics.parquet'))

    association = None
    if len(columns) == 2 and columns[0] == 'lang' and {'en·yes', 'en·no', 'zh·yes', 'zh·no'} <= set(model.levels):
        association = pd.DataFrame({lang: prevalence.loc[f'{lang}·yes'] - prevalence.loc[f'{lang}·no']
                                    for lang in ('en', 'zh')})
        association['gap'] = association['zh'] - association['en']
        association.round(4).to_csv(os.path.join(out, 'association.tsv'), sep='\t')
    for k in range(args.topics):
        terms = ', '.join(topics.loc[topics['topic'] == k, 'term'].head(args.top))
        shares = '  '.join(f'{lv} {prevalence.loc[lv, f"t{k}"]:.3f}' for lv in model.levels)
        assoc = '' if association is None else (f"  | {columns[1]}-association en {association.loc[f't{k}', 'en']:+.3f}"
                                                f" zh {association.loc[f't{k}', 'zh']:+.3f}")
        print(f'\nt{k}: {terms}\n    prevalence {shares}{assoc}')
    print(f'\n-> {out}/{{topics,labels,prevalence{",association" if association is not None else ""}}}.tsv, '
          f'doc_topics.parquet')


if __name__ == '__main__':
    main()
