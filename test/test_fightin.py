"""Run from the repo root: python -m pytest test/"""
import numpy as np

from src.fightin.counts import GroupCounts, count
from src.fightin.measures import (difference_of_proportions, log_odds_dirichlet, log_odds_laplace, log_odds_ratio,
                                  tf_idf, top_words, wordscores)


def corpus(seed=0):
    """Two groups sharing 300 common words; both say 'women' and 'babi', group i 'women' far more, group j 'babi';
    a few rare words one group used once or twice (the obscure words that dominate the naive measures)."""
    rng = np.random.default_rng(seed)
    common = [f'w{k}' for k in range(300)]
    weights = 1 / np.arange(1, 301)
    weights /= weights.sum()
    docs_i = [list(rng.choice(common, 200, p=weights)) + ['women'] * 8 + ['babi'] + ['the'] * 30 for _ in range(50)]
    docs_j = [list(rng.choice(common, 200, p=weights)) + ['babi'] * 8 + ['women'] + ['the'] * 31 for _ in range(50)]
    docs_i[0] += ['bankruptci'] * 5           # used 5 times, by one group only
    docs_j[0] += ['infant'] * 5
    return count(docs_i, docs_j)


def test_counts_share_one_vocabulary():
    c = count([['a', 'b', 'b']], [['b', 'c']])
    assert c.words == ['a', 'b', 'c'] and list(c.i) == [1, 2, 0] and list(c.j) == [0, 1, 1]


def test_z_scores_find_the_partisan_words_not_rare_or_frequent_ones():
    c = corpus()
    lo = log_odds_dirichlet(c)
    i_words, j_words = top_words(c, lo.z, k=1)
    assert i_words[0][0] == 'women' and j_words[0][0] == 'babi'
    # the smoothed log-odds-ratio is topped by the rare words only one group used (the paper's Fig. 2)
    raw_i, raw_j = top_words(c, log_odds_ratio(c), k=1)
    assert raw_i[0][0] == 'bankruptci' and raw_j[0][0] == 'infant'
    # the difference of proportions favours frequent words: 'the' outranks 'babi' in j's direction
    assert abs(difference_of_proportions(c)[c.words.index('the')]) > 0
    assert abs(lo.z[c.words.index('the')]) < 2      # 'the', used about equally: not significant


def test_dirichlet_formulas():
    c = GroupCounts(['a', 'b'], np.array([10.0, 90.0]), np.array([30.0, 70.0]))
    lo = log_odds_dirichlet(c, alpha=[1.0, 1.0])
    a0 = 2.0
    expected = np.log(11 / (100 + a0 - 11)) - np.log(31 / (100 + a0 - 31))
    assert np.isclose(lo.delta[0], expected)
    assert np.isclose(lo.variance[0], 1 / 11 + 1 / (102 - 11) + 1 / 31 + 1 / (102 - 31))
    assert np.isclose(lo.z[0], expected / np.sqrt(lo.variance[0])) and lo.z[0] < 0


def test_an_informative_prior_shrinks_rare_words_more():
    c = corpus()
    weak, strong = log_odds_dirichlet(c), log_odds_dirichlet(c, alpha0=5000)
    rare = c.words.index('bankruptci')
    assert abs(strong.delta[rare]) < abs(weak.delta[rare])


def test_wordscores_and_tf_idf():
    c = GroupCounts(['only_i', 'shared', 'only_j'], np.array([5.0, 5.0, 0.0]), np.array([0.0, 5.0, 5.0]))
    assert list(wordscores(c)) == [1.0, 0.0, -1.0]
    assert tf_idf(c, 'nnn')[0] > 0 > tf_idf(c, 'nnn')[2] and tf_idf(c, 'ntn')[1] == 0     # log(1/1) = 0


def test_the_laplace_prior_zeroes_most_words():
    c = corpus()
    delta = log_odds_laplace(c, gamma=30.0)
    assert np.mean(delta == 0) > 0.8
    assert delta[c.words.index('women')] > 0 > delta[c.words.index('babi')]
