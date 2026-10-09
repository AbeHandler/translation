"""
Semantic axes (after SemAxis, An et al. 2018): a direction in a multilingual embedding space from one pole to
another (competition -> cooperation), each pole the centroid of seed words in English and Chinese. A concept's
score is the cosine between its vector and the axis: > 0 leans to the positive pole.
"""
import numpy as np


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def axis_vector(encode, negative, positive):
    """The unit direction from the negative pole's centroid to the positive one's. negative, positive: seed lists."""
    return unit(unit(encode(positive)).mean(0) - unit(encode(negative)).mean(0))


def scores(encode, terms, axis):
    """Each term's cosine with the axis."""
    return unit(encode(list(terms))) @ axis


def bootstrap_corr(x, y, n=2000, seed=0):
    """(Spearman correlation of x and y, its 95% interval by resampling the items)."""
    from scipy.stats import spearmanr
    x, y = np.asarray(x), np.asarray(y)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n):
        k = rng.integers(0, len(x), len(x))
        draws.append(spearmanr(x[k], y[k]).statistic)
    return spearmanr(x, y).statistic, np.nanpercentile(draws, [2.5, 97.5])
