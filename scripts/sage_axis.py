#!/usr/bin/env python
"""
Does a covariate's English-Chinese difference follow a semantic axis? Scores each concept of a joint SAGE
comparison (scripts/sage_crosslingual.py compare.tsv) on an axis (config/axes.yaml, src/sage/axes.py: e.g.
competition -> cooperation), then relates the axis to the concepts' distinctiveness:
    corr(score, D_en), corr(score, D_zh)   which pole each language's covariate coverage leans to
    corr(score, gap)                        > 0: the more cooperation-like a concept, the more covariate-like in
                                            Chinese than in English (gap = D_zh - D_en)
Spearman correlations with 95% intervals (bootstrap over concepts), over concepts used -min-uses+ times in each
language x covariate cell. Also the concepts nearest each pole, with their D values.
-> results/sage_axis/<experiment>/<axis>.tsv

Run as a module from the repo root:
    python -m scripts.sage_axis -compare results/sage_crosslingual/nvidia/compare.tsv -experiment-name nvidia
"""
import argparse
import os

import pandas as pd
import yaml

from config.paths import REPO_ROOT
from src.fightin.concepts import for_embedding
from src.sage.axes import axis_vector, bootstrap_corr, scores

NAME = 'sage_axis'


def parse_args():
    parser = argparse.ArgumentParser(description="A covariate's English-Chinese difference along a semantic axis")
    parser.add_argument('-compare', required=True, help='scripts/sage_crosslingual.py compare.tsv')
    parser.add_argument('-axes', default=os.path.join(REPO_ROOT, 'config', 'axes.yaml'))
    parser.add_argument('-axis', default='competition_cooperation')
    parser.add_argument('-min-uses', type=int, default=5, help='in each language x covariate cell')
    parser.add_argument('-exclude', default='nvidia|jensen|huang', help='concepts left out (the subject itself)')
    parser.add_argument('-top', type=int, default=25)
    parser.add_argument('-experiment-name', required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    from src.dispersion.encoders import labse
    labse_encode = labse()

    def encode(texts):
        return labse_encode([for_embedding(t) for t in texts])
    spec = yaml.safe_load(open(args.axes))[args.axis]
    axis = axis_vector(encode, spec['negative']['en'] + spec['negative']['zh'],
                       spec['positive']['en'] + spec['positive']['zh'])
    table = pd.read_csv(args.compare, sep='\t', keep_default_na=False)
    cells = ['en_yes', 'en_no', 'zh_yes', 'zh_no']
    table = table[(table[cells] >= args.min_uses).all(1)]
    if args.exclude:
        table = table[~table['concept'].str.contains(args.exclude, case=False)]
    table = table.assign(score=scores(encode, table['concept'], axis)).sort_values('score')
    out = os.path.join(REPO_ROOT, 'results', NAME, args.experiment_name)
    os.makedirs(out, exist_ok=True)
    table.round(3).to_csv(os.path.join(out, f'{args.axis}.tsv'), sep='\t', index=False)

    print(f'{args.axis}: {len(table)} concepts with {args.min_uses}+ uses in every cell; score < 0 leans negative '
          f'(first pole), > 0 positive')
    for column, meaning in (('D_en', 'English: covariate-likeness'), ('D_zh', 'Chinese: covariate-likeness'),
                            ('gap', 'gap (D_zh - D_en)')):
        r, (lo, hi) = bootstrap_corr(table['score'], table[column])
        print(f'  corr(score, {column:4}) = {r:+.3f}  [{lo:+.3f}, {hi:+.3f}]   {meaning}')
    for title, rows in (('nearest the negative pole', table.head(args.top)),
                        ('nearest the positive pole', table.tail(args.top)[::-1])):
        print(f'\n=== {title}: concept [Chinese forms] score  D_en / D_zh  gap')
        print('; '.join(f"{r.concept}{f' [{r.zh_forms.split()[0]}]' if r.zh_forms else ''} {r.score:+.2f} "
                        f'{r.D_en:+.1f}/{r.D_zh:+.1f} {r.gap:+.1f}' for r in rows.itertuples()))
    print(f"\n-> {os.path.join(out, args.axis + '.tsv')}")


if __name__ == '__main__':
    main()
