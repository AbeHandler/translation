#!/usr/bin/env python
"""
Fit model1 (src/transmission/model1.py, docs/model1.md) to a pair table and write each pair's posterior r_ij =
P(English doc i transmits Chinese doc j).
    -pairs  CSV doc_en, doc_zh, L, c, y (scripts/build_transmission_pairs.py)
    -out    the same CSV plus r
Prints the parameters, whether the log-likelihood ever decreased, and a held-out check of the labels (grouped by
English document, so a document's pairs are never split across folds).

Run as a module from the repo root:
    python -m scripts.fit_model1 -pairs /tmp/transmission_pairs.csv
    python -m scripts.fit_model1 -fake          # data drawn from the model itself: does EM recover it?
"""
import argparse

import numpy as np

from config.paths import TRANSMISSION_PAIRS_PATH
from src.transmission.model1 import EPS, evaluate, fake_data, fit
from src.transmission.pairs import read_pairs, write_pairs


def parse_args():
    parser = argparse.ArgumentParser(description='Fit model1 to a pair table')
    parser.add_argument('-pairs', default=str(TRANSMISSION_PAIRS_PATH))
    parser.add_argument('-out', default='', help='default: <pairs>.r.csv')
    parser.add_argument('-eps', type=float, default=EPS, help='gamma_0, the fixed chance-copy rate')
    parser.add_argument('-fake', action='store_true', help='fit fake data drawn from the model instead')
    return parser.parse_args()


def main():
    args = parse_args()
    if args.fake:
        L, c, y, truth = fake_data(eps=args.eps)
        rows, groups = None, np.arange(len(y)) // 10
    else:
        rows, L, c, y = read_pairs(args.pairs)
        truth, groups = None, np.array([r['doc_en'] for r in rows])

    params, r, history = fit(L, c, y, eps=args.eps)
    steps = np.diff(history)
    print(f'{len(history) - 1} iterations; log-likelihood {history[0]:.2f} -> {history[-1]:.2f}; '
          f'never decreased: {bool((steps >= -1e-9).all())}')
    print(f'pi0    p(transmits | no link)  {params.pi0:.3f}')
    print(f'pi1    p(transmits | link)     {params.pi1:.3f}')
    print(f'gamma1 p(copies | transmits)   {params.gamma1:.3f}')
    unlabelled = np.isnan(y)
    print(f'{int(((r > 0.5) & unlabelled & (L == 0)).sum())} unlinked, unlabelled pairs with r > 0.5 '
          f'(candidate missing links); {int(((r > 0.1) & (r < 0.9) & unlabelled).sum())} ambiguous (0.1 < r < 0.9)')
    if truth is not None:
        print(f'fake data, true values pi0 0.05, pi1 0.60, gamma1 0.25; accuracy on unlabelled pairs: '
              f'{((r[unlabelled] > 0.5) == truth[unlabelled]).mean():.1%}')
    if (~unlabelled).sum() >= 2:
        print('held-out labels:', {k: round(v, 3) for k, v in evaluate(L, c, y, groups, eps=args.eps).items()})
    if rows is not None:
        out = args.out or args.pairs.replace('.csv', '.r.csv')
        write_pairs([{**row, 'r': f'{ri:.4f}'} for row, ri in zip(rows, r)], out)
        print(f'-> {out}')


if __name__ == '__main__':
    main()
