#!/usr/bin/env python
"""
Compare a covariate's distinctiveness across languages (difference in differences): for each concept, its SAGE
contrast in English (D_en = eta_yes - eta_no, from scripts/sage_covariate.py contrast_<facet>.tsv) and in Chinese
(D_zh), Chinese phrases put on English concepts by a fightin concepts table (word -> concept, cosine >= -threshold;
Latin-script phrases, e.g. known names, are their own concept). A concept's phrases are pooled (count-weighted).
A concept missing from one language's contrast has D = 0 there (SAGE left it at the background), but the gap lists
keep concepts found in both languages' results: a phrase only one language forms (nvidia芯片, "deals black friday")
would otherwise top them.
    gap = D_zh - D_en: > 0 tied to the covariate more in Chinese coverage, < 0 more in English
-> results/sage_compare/<experiment>/compare.tsv

Run as a module from the repo root:
    python -m scripts.sage_compare -en results/sage_covariate/en_nvidia/contrast_nvidia.tsv \\
        -zh results/sage_covariate/zh_nvidia/contrast_nvidia.tsv \\
        -concepts /tmp/fightin/all_5k/concepts_ngrams2-3.tsv -experiment-name nvidia
"""
import argparse
import os

import pandas as pd

from config.paths import REPO_ROOT
from src.fightin.concepts import LATIN

NAME = 'sage_compare'


def parse_args():
    parser = argparse.ArgumentParser(description="A covariate's distinctiveness, English vs Chinese")
    parser.add_argument('-en', required=True)
    parser.add_argument('-zh', required=True)
    parser.add_argument('-concepts', required=True, help='a fightin concepts_<unit>.tsv: word, concept, similarity')
    parser.add_argument('-threshold', type=float, default=0.7)
    parser.add_argument('-min-count', type=int, default=15, help='uses at the covariate level, in some language')
    parser.add_argument('-top', type=int, default=40)
    parser.add_argument('-experiment-name', required=True)
    return parser.parse_args()


def concept_of(term, mapping):
    if all(LATIN.match(w) for w in term.split()):
        return term
    return mapping.get(term, term)


def pooled(table, mapping=None):
    """concept -> D (count-weighted over its phrases), uses at yes and no, its phrases."""
    table = table.copy()
    table['concept'] = table['term'].map(lambda t: concept_of(t, mapping) if mapping else t)
    table['weight'] = table['count_yes'] + table['count_no'] + 1
    table['wd'] = table['difference'] * table['weight']
    out = table.groupby('concept').agg(wd=('wd', 'sum'), weight=('weight', 'sum'), yes=('count_yes', 'sum'),
                                       no=('count_no', 'sum'), forms=('term', lambda t: ' '.join(t.head(3))))
    out['D'] = out['wd'] / out['weight']
    return out[['D', 'yes', 'no', 'forms']]


def main():
    args = parse_args()
    concepts = pd.read_csv(args.concepts, sep='\t', usecols=['word', 'concept', 'similarity'])
    mapping = dict(zip(concepts.loc[concepts['similarity'] >= args.threshold, 'word'],
                       concepts.loc[concepts['similarity'] >= args.threshold, 'concept']))
    en = pooled(pd.read_csv(args.en, sep='\t', keep_default_na=False))
    zh = pooled(pd.read_csv(args.zh, sep='\t', keep_default_na=False), mapping)
    both = en.join(zh, how='outer', lsuffix='_en', rsuffix='_zh')
    both['in_both'] = both['D_en'].notna() & both['D_zh'].notna()
    for col in ('D_en', 'D_zh', 'yes_en', 'no_en', 'yes_zh', 'no_zh'):
        both[col] = both[col].fillna(0)
    both['forms_zh'] = both['forms_zh'].fillna('')
    both['gap'] = both['D_zh'] - both['D_en']
    both = both[(both['yes_en'] >= args.min_count) | (both['yes_zh'] >= args.min_count)]
    both = both.drop(columns=['forms_en']).sort_values('gap', ascending=False).round(3)
    out = os.path.join(REPO_ROOT, 'results', NAME, args.experiment_name)
    os.makedirs(out, exist_ok=True)
    both.to_csv(os.path.join(out, 'compare.tsv'), sep='\t')
    shared = both[(both['D_en'] > 1) & (both['D_zh'] > 1)].sort_values('D_en', ascending=False)
    found = both[both['in_both']]
    for title, rows in (('tied to it more in Chinese (gap > 0)', found.head(args.top)),
                        ('tied to it more in English (gap < 0)', found.tail(args.top)[::-1]),
                        ('tied to it in both (D > 1 in each)', shared.head(args.top))):
        print(f'\n=== {title}: concept [Chinese forms] D_en / D_zh (uses at yes: en / zh)')
        print(', '.join(f"{c}{f' [{f}]' if f and f != c else ''} {r.D_en:+.1f}/{r.D_zh:+.1f} "
                        f"({int(r.yes_en)}/{int(r.yes_zh)})" for c, r, f in
                        zip(rows.index, rows.itertuples(), rows['forms_zh'])))
    print(f"\n{len(both)} concepts, {len(found)} in both languages' results -> {os.path.join(out, 'compare.tsv')}")


if __name__ == '__main__':
    main()
