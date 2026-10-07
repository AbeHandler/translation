"""
A demo of Fightin' Words on a made-up two-group corpus, after the paper's Figures 1-6: both groups share common
words; group i favours 'women', group j 'babi'; both say 'the' a lot; each group used one obscure word five times.
Each measure's top words for each group show its failure mode: the difference of proportions favours frequent
words, the log-odds-ratio and WordScores obscure ones, while the z-scores of the Dirichlet-prior log-odds and the
Laplace prior pick out the partisan words.

Run from the repo root:
    python -m src.fightin.demo
"""
import numpy as np

from src.fightin.counts import count
from src.fightin.measures import (difference_of_proportions, log_odds_dirichlet, log_odds_laplace, log_odds_ratio,
                                  top_words, wordscores)


def corpus(seed=0):
    rng = np.random.default_rng(seed)
    common = [f'w{k}' for k in range(300)]
    weights = 1 / np.arange(1, 301)
    weights /= weights.sum()
    docs_i = [list(rng.choice(common, 200, p=weights)) + ['women'] * 8 + ['babi'] + ['the'] * 30 for _ in range(50)]
    docs_j = [list(rng.choice(common, 200, p=weights)) + ['babi'] * 8 + ['women'] + ['the'] * 33 for _ in range(50)]
    docs_i[0] += ['bankruptci'] * 5
    docs_j[0] += ['infant'] * 5
    return count(docs_i, docs_j)


def main():
    c = corpus()
    measures = {'difference of proportions': difference_of_proportions(c), 'log-odds-ratio': log_odds_ratio(c),
                'WordScores': wordscores(c), 'log-odds, Dirichlet prior (z)': log_odds_dirichlet(c).z,
                'log-odds, informative prior (z)': log_odds_dirichlet(c, alpha0=1000).z,
                'log-odds, Laplace prior': log_odds_laplace(c, gamma=30.0)}
    for name, scores in measures.items():
        top_i, top_j = top_words(c, scores, k=4)
        print(f'{name:32} i: {", ".join(w for w, _ in top_i):34} j: {", ".join(w for w, _ in top_j)}')
    print(f'\nLaplace prior: {np.mean(measures["log-odds, Laplace prior"] == 0):.0%} of words shrunk exactly to 0')


if __name__ == '__main__':
    main()
