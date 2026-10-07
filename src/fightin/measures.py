"""
The feature-evaluation measures of Fightin' Words, for two groups i and j (section numbers and equations from the
paper). Each takes GroupCounts (src/fightin/counts.py) and returns a W-vector: positive = more typical of group i.

Non-model-based (sec. 3.2), which the paper shows are dominated by frequent or by rare words:
    difference_of_proportions   f_i - f_j                                        (3.2.2)
    log_odds_ratio              log of the odds ratio, eps added to every count     (3.2.5)
    tf_idf                      'ntn' (logged df) or 'nnn' (unlogged)            (3.2.7, eqs. 1-2)
    wordscores                  raw WordScores, group i at +1 and j at -1       (3.2.8, eq. 3)
Model-based (sec. 3.3-3.5), recommended:
    log_odds_dirichlet          log-odds-ratio with a Dirichlet prior, its variance and z-score (eqs. 16, 19,
                                22): uninformative (alpha_w = a for all w) or informative (alpha_w proportional to
                                a background's word frequencies, eq. 23)
    log_odds_laplace            log-odds-ratio with a Laplace prior: most words shrunk exactly to zero (3.5.2;
                                gamma fixed here, rather than given a hyperprior)
"""
from dataclasses import dataclass

import numpy as np


def _proportions(y):
    return y / y.sum()


def difference_of_proportions(c):
    return _proportions(c.i) - _proportions(c.j)


def log_odds_ratio(c, eps=0.5):
    """The smoothed observed log-odds-ratio: eps added to every count ("add a little bit to the zeroes")."""
    fi, fj = _proportions(c.i + eps), _proportions(c.j + eps)
    return np.log(fi / (1 - fi)) - np.log(fj / (1 - fj))


def tf_idf(c, variant='nnn'):
    """tf.idf of group i minus that of group j, with df the share of the two groups using the word (eqs. 1-2):
    'ntn' logs the idf, 'nnn' doesn't."""
    df = ((c.i > 0).astype(float) + (c.j > 0)) / 2
    idf = np.log(1 / df) if variant == 'ntn' else 1 / df
    return _proportions(c.i) * idf - _proportions(c.j) * idf


def wordscores(c):
    """Raw WordScores with group i at +1, j at -1 (eq. 3); 0 for words neither group uses."""
    fi, fj = _proportions(c.i), _proportions(c.j)
    total = fi + fj
    return np.divide(fi - fj, total, out=np.zeros_like(total), where=total > 0)


@dataclass
class LogOdds:
    delta: np.ndarray      # the log-odds-ratio, i vs j
    variance: np.ndarray   # its approximate variance (eq. 19)
    z: np.ndarray          # delta / sqrt(variance) (eq. 22): the recommended evaluation measure


def dirichlet_prior(c, alpha0=None, a=0.01):
    """The prior's alpha_w: informative when alpha0 is given (alpha0 times the background's word proportions;
    eq. 23, the background being c.background, or i + j), else uninformative (a for every word)."""
    if alpha0 is None:
        return np.full(len(c.words), a)
    background = c.background if c.background is not None else c.i + c.j
    return alpha0 * _proportions(background) + 1e-12      # every alpha_w > 0


def log_odds_dirichlet(c, alpha=None, alpha0=None, a=0.01):
    """The log-odds-ratio of word use between groups i and j with a Dirichlet prior (eq. 16), its variance (eq. 19)
    and z-score (eq. 22). alpha: the prior's W-vector (default dirichlet_prior(c, alpha0, a): informative with
    alpha0, else uninformative with a)."""
    alpha = dirichlet_prior(c, alpha0, a) if alpha is None else np.asarray(alpha, dtype=float)
    a0 = alpha.sum()
    ni, nj = c.i.sum(), c.j.sum()
    yi, yj = c.i + alpha, c.j + alpha
    rest_i, rest_j = ni + a0 - yi, nj + a0 - yj
    delta = np.log(yi / rest_i) - np.log(yj / rest_j)
    variance = 1 / yi + 1 / rest_i + 1 / yj + 1 / rest_j
    return LogOdds(delta, variance, delta / np.sqrt(variance))


def log_odds_laplace(c, gamma=50.0, steps=5000, lr=None, tol=1e-9):
    """The log-odds-ratio of groups i and j with a Laplace prior (sec. 3.5.2): each group's multinomial log-odds
    beta^(g) is the posterior mode under Laplace(beta_MLE of the pooled counts, gamma), found by proximal gradient
    ascent (soft-thresholding towards the pooled estimate); most words end exactly at the pooled value, so their
    log-odds-ratio is exactly 0. A larger gamma zeroes more words. The paper puts a hyperprior on gamma; here it
    is fixed. Returns delta = beta^(i) - beta^(j), relative to the pooled log-odds."""
    pooled = c.i + c.j + 1e-9
    prior_mode = np.log(pooled / pooled.sum())

    def mode(y):
        n = y.sum()
        beta = prior_mode.copy()
        step = lr or 1.0 / n                      # the multinomial log-likelihood's gradient is n-Lipschitz
        for _ in range(steps):
            p = np.exp(beta - beta.max())
            p /= p.sum()
            moved = beta + step * (y - n * p)    # gradient of sum y log softmax(beta)
            shrunk = prior_mode + np.sign(moved - prior_mode) * np.maximum(np.abs(moved - prior_mode) - step * gamma, 0)
            if np.max(np.abs(shrunk - beta)) < tol:
                return shrunk
            beta = shrunk
        return beta
    return mode(c.i) - mode(c.j)


def top_words(c, scores, k=20):
    """The k words most typical of group i and of group j by a score: ([(word, score)], [(word, score)])."""
    order = np.argsort(scores)
    return ([(c.words[w], float(scores[w])) for w in order[::-1][:k]],
            [(c.words[w], float(scores[w])) for w in order[:k]])
