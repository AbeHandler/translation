#!/usr/bin/env python
"""
Fit model1 (src/model/model1.py, docs/model1.md), the latent-class model of transmission, to the candidate pairs'
feature matrix and write each pair's posterior r = P(English doc transmits Chinese doc).
    -pairs  CSV doc_en, doc_zh, link, copy, similarity, date_gap, y (scripts/build_transmission_pairs.py)
    -out    the same CSV plus r
Prints the prior, each feature's distribution given z and its likelihood ratios, and whether the likelihood ever
decreased. Identical rows are fit once, with a weight.

Run as a module from the repo root:
    python -m scripts.fit_model1 -pairs /tmp/transmission_pairs.csv
    python -m scripts.fit_model1 -fake          # data drawn from the model itself: does EM recover it?
"""
import argparse

import numpy as np

from config.paths import TRANSMISSION_PAIRS_PATH
from src.features.pairs import FEATURES, N_LEVELS, POSITIVE_HINT, aggregate, read_pairs, write_pairs
from src.model.model1 import fake_data, fit, likelihood_ratios


def parse_args():
    parser = argparse.ArgumentParser(description='Fit model1 to the candidate pairs')
    parser.add_argument('-pairs', default=str(TRANSMISSION_PAIRS_PATH))
    parser.add_argument('-out', default='', help='default: <pairs>.r.csv')
    parser.add_argument('-fake', action='store_true', help='fit fake data drawn from the model instead')
    return parser.parse_args()


def main():
    args = parse_args()
    if args.fake:
        X, y, z, n_levels, truth = fake_data()
        names, hint = [f'f{k}' for k in range(len(n_levels))], {0: [1], 1: [1], 2: [1], 3: [3]}
    else:
        pairs, X, extra = read_pairs(args.pairs)
        y = np.array([float(v) if str(v).strip() != '' else np.nan for v in extra.get('y', [''] * len(pairs))])
        names, n_levels, hint = FEATURES, N_LEVELS, POSITIVE_HINT

    Xu, yu, w, row_of = aggregate(X, y)
    params, r_unique, history = fit(Xu, yu, n_levels, w=w, positive_hint=hint)
    r = r_unique[row_of]
    print(f'{len(y)} pairs ({len(w)} distinct rows), {int((~np.isnan(y)).sum())} labelled; '
          f'{len(history) - 1} iterations, never decreased: {bool((np.diff(history) >= -1e-6).all())}')
    print(f'pi = p(transmits) {params.pi:.3f}')
    for name, th, ratio in zip(names, params.theta, likelihood_ratios(params)):
        print(f'  {name:11} p(x|z=0) {np.round(th[0], 3).tolist()}  p(x|z=1) {np.round(th[1], 3).tolist()}  '
              f'ratio {np.round(ratio, 2).tolist()}')
    print(f'{int((r > 0.5).sum())} pairs with r > 0.5; {int(((r > 0.1) & (r < 0.9)).sum())} ambiguous (0.1 < r < 0.9)')
    if args.fake:
        print(f'true pi 0.02; accuracy {((r > 0.5) == z).mean():.1%}')
        return
    out = args.out or args.pairs.replace('.csv', '.r.csv')
    write_pairs(out, pairs, X, {**extra, 'r': [f'{v:.4f}' for v in r]})
    print(f'-> {out}')


if __name__ == '__main__':
    main()
