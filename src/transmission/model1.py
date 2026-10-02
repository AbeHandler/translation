"""
model1: does English document i transmit information from Chinese document j? Semi-supervised EM over pairs
(spec: docs/model1.md). The model layer: arrays in, parameters and posteriors out; no files, no pair building.

Per pair: L (link, a covariate), c (copied Chinese string, observed), y (hand label for z, NaN if none).
    p(z=1 | L=l) = pi_l          c | z ~ Bernoulli(gamma_z), gamma_0 = eps fixed, gamma_1 free
Free parameters: pi0, pi1, gamma1. EM never decreases the conditional log-likelihood of c given L, with z
clamped to y where labelled; fit() records it at every iteration.
"""
from dataclasses import dataclass

import numpy as np

EPS = 1e-3      # gamma_0: chance-copy rate, fixed (chance copying of >= 4 Chinese characters is near zero)
TINY = 1e-9     # probabilities are kept in [TINY, 1 - TINY] so logs stay finite


@dataclass
class Params:
    pi0: float = 0.05    # p(transmits | no link)
    pi1: float = 0.5     # p(transmits | link)
    gamma1: float = 0.2  # p(copies | transmits)

    @classmethod
    def from_labels(cls, L, c, y, min_positives=30):
        """Initial values from the labelled pairs if there are enough positives, else the spec's defaults."""
        lab = ~np.isnan(y)
        if (y[lab] == 1).sum() < min_positives:
            return cls()

        def rate(values, mask, default):
            return float(np.clip(values[mask].mean(), 0.01, 0.99)) if mask.any() else default
        return cls(pi0=rate(y, lab & (L == 0), cls.pi0), pi1=rate(y, lab & (L == 1), cls.pi1),
                   gamma1=rate(c, lab & (y == 1), cls.gamma1))


def _terms(params, L, c, eps):
    pi = np.where(L == 1, params.pi1, params.pi0)    # p(z=1 | L)
    a = np.where(c == 1, params.gamma1, 1 - params.gamma1)    # p(c | z=1)
    b = np.where(c == 1, eps, 1 - eps)               # p(c | z=0)
    return pi, a, b


def loglik(params, L, c, y, eps=EPS):
    """log p(c | L), summing z out for unlabelled pairs and fixing z = y for labelled ones."""
    pi, a, b = _terms(params, L, c, eps)
    labelled = np.where(y == 1, np.log(pi * a), np.log((1 - pi) * b))
    return float(np.where(np.isnan(y), np.log(pi * a + (1 - pi) * b), labelled).sum())


def posterior(params, L, c, y, eps=EPS):
    """r = p(z=1 | L, c), or y where labelled."""
    pi, a, b = _terms(params, L, c, eps)
    return np.where(np.isnan(y), pi * a / (pi * a + (1 - pi) * b), y)


def _clip(v):
    return float(np.clip(v, TINY, 1 - TINY))


def m_step(r, L, c, params):
    return Params(pi0=_clip(r[L == 0].mean()) if (L == 0).any() else params.pi0,
                  pi1=_clip(r[L == 1].mean()) if (L == 1).any() else params.pi1,
                  gamma1=_clip((r * c).sum() / r.sum()) if r.sum() > 0 else params.gamma1)


def fit(L, c, y, init=None, eps=EPS, tol=1e-8, max_iter=200):
    """EM. Returns (params, r, log-likelihood after each iteration, starting with the initial one)."""
    L, c, y = (np.asarray(v, dtype=float) for v in (L, c, y))
    params = init or Params.from_labels(L, c, y)
    history = [loglik(params, L, c, y, eps)]
    for _ in range(max_iter):
        params = m_step(posterior(params, L, c, y, eps), L, c, params)
        history.append(loglik(params, L, c, y, eps))
        if abs(history[-1] - history[-2]) < tol:
            break
    return params, posterior(params, L, c, y, eps), np.array(history)


def evaluate(L, c, y, groups, eps=EPS, n_folds=5, seed=0):
    """Held-out check: labelled pairs of one group fold at a time (groups: e.g. English doc or outlet) are
    treated as unlabelled, the model is refit, and their r is compared with y. Returns precision and recall at
    r > 0.5, the mean |r - y| (calibration), and the share of unlabelled pairs with 0.1 < r < 0.9."""
    L, c, y = (np.asarray(v, dtype=float) for v in (L, c, y))
    groups = np.asarray(groups)
    labelled = ~np.isnan(y)
    names = np.unique(groups[labelled])
    np.random.default_rng(seed).shuffle(names)
    r_held = np.full(len(y), np.nan)
    for fold in np.array_split(names, min(n_folds, len(names))):
        held = labelled & np.isin(groups, fold)
        _, r, _ = fit(L, c, np.where(held, np.nan, y), eps=eps)
        r_held[held] = r[held]
    pred, truth = r_held[labelled] > 0.5, y[labelled] == 1
    _, r_all, _ = fit(L, c, y, eps=eps)
    unlabelled = r_all[~labelled]
    return {'labelled': int(labelled.sum()),
            'precision': float((pred & truth).sum() / max(pred.sum(), 1)),
            'recall': float((pred & truth).sum() / max(truth.sum(), 1)),
            'mean_abs_error': float(np.abs(r_held[labelled] - y[labelled]).mean()),
            'ambiguous_share': float(((unlabelled > 0.1) & (unlabelled < 0.9)).mean()) if len(unlabelled) else 0.0}


def fake_data(n=3000, n_labelled=300, pi0=0.05, pi1=0.6, gamma1=0.25, eps=EPS, seed=0):
    """Pairs drawn from the model itself, for checks: (L, c, y, z)."""
    rng = np.random.default_rng(seed)
    L = (rng.random(n) < 0.2).astype(float)
    z = rng.random(n) < np.where(L == 1, pi1, pi0)
    c = (rng.random(n) < np.where(z, gamma1, eps)).astype(float)
    y = np.full(n, np.nan)
    idx = rng.choice(n, n_labelled, replace=False)
    y[idx] = z[idx]
    return L, c, y, z
