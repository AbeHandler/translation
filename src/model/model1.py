"""
model1: does English document i transmit information from Chinese document j? A latent-class (naive Bayes)
model fit with semi-supervised EM (spec: docs/model1.md). The model layer: arrays in, parameters and posteriors
out; the features come from src/features/ (pairs.py).

Generative story, per pair:
    z ~ Bernoulli(pi)                                     transmits or not
    x_k | z ~ Categorical(theta_k[z])  for each feature k  independently given z (naive Bayes)
Features are small integer codes (binary signals, or binned scores); -1 means missing and the feature is left
out of that pair's likelihood. Hand labels y fix z where given. A row may stand for w identical pairs (w).

Most pairs are not transmissions, so theta_k[0] is close to the features' distribution over all pairs; EM learns
theta_k[1], what transmitters look like, from the excess of co-occurring signals, and combines the signals into
r = p(z=1 | x). A feature's theta_k[z] can be fixed (e.g. copying under z=0 at a small eps).
"""
from dataclasses import dataclass, field

import numpy as np

ALPHA = 0.01    # Dirichlet smoothing added to the expected counts in the M-step, so no probability is 0
TINY = 1e-12


@dataclass
class Params:
    pi: float
    theta: list = field(default_factory=list)   # per feature: array (2, n_levels), rows z=0 and z=1


def initial_params(n_levels, positive_hint, pi=0.01):
    """Uniform theta for z=0; for z=1, each feature leans towards the levels in positive_hint[k] (the levels
    that suggest transmission: link = 1, copy = 1, top similarity bins). This also names the positive class, so
    EM can't swap the two components."""
    theta = []
    for k, n in enumerate(n_levels):
        neg = np.full(n, 1.0 / n)
        pos = np.ones(n)
        pos[list(positive_hint.get(k, []))] = 4.0
        theta.append(np.vstack([neg, pos / pos.sum()]))
    return Params(pi=pi, theta=theta)


def _log_lik_by_class(params, X):
    """(n, 2): log p(x | z) for z = 0, 1, leaving missing features (-1) out."""
    out = np.zeros((X.shape[0], 2))
    for k, th in enumerate(params.theta):
        present = X[:, k] >= 0
        out[present] += np.log(th[:, X[present, k]].T + TINY)
    return out


def _joint(params, X):
    ll = _log_lik_by_class(params, X)
    return np.log(params.pi) + ll[:, 1], np.log(1 - params.pi) + ll[:, 0]   # log p(z=1, x), log p(z=0, x)


def posterior(params, X, y):
    """r = p(z=1 | x), or y where labelled."""
    a, b = _joint(params, X)
    return np.where(np.isnan(y), 1 / (1 + np.exp(b - a)), y)


def loglik(params, X, y, w):
    """log p(x), summing z out for unlabelled rows and fixing z = y for labelled ones; rows weighted by w."""
    a, b = _joint(params, X)
    terms = np.where(np.isnan(y), np.logaddexp(a, b), np.where(y == 1, a, b))
    return float((terms * w).sum())


def objective(params, X, y, w, fixed, alpha=ALPHA):
    """What EM increases: the log-likelihood plus the log of the Dirichlet(1 + alpha) prior on the free theta
    (the M-step adds alpha to the expected counts, so it maximizes this, not the bare log-likelihood)."""
    prior = sum(alpha * np.log(th[z]).sum() for k, th in enumerate(params.theta) for z in (0, 1)
                if z not in fixed.get(k, {}))
    return loglik(params, X, y, w) + prior


def m_step(r, X, w, n_levels, fixed, alpha=ALPHA):
    pi = float(np.clip((r * w).sum() / w.sum(), TINY, 1 - TINY))
    theta = []
    for k, n in enumerate(n_levels):
        present = X[:, k] >= 0
        counts = np.full((2, n), alpha)
        for z, weight in ((0, (1 - r) * w), (1, r * w)):
            np.add.at(counts[z], X[present, k], weight[present])
        th = counts / counts.sum(axis=1, keepdims=True)
        for z, probs in fixed.get(k, {}).items():
            th[z] = probs
        theta.append(th)
    return Params(pi=pi, theta=theta)


def fit(X, y, n_levels, w=None, init=None, fixed=None, positive_hint=None, tol=1e-8, max_iter=500):
    """EM. X: (n, n_features) int codes, -1 missing; y: labels with NaN; fixed: {feature: {z: probs}}.
    Returns (params, r, the objective (log-likelihood + log-prior, see objective()) after each iteration,
    starting with the initial one). The objective never decreases."""
    X = np.asarray(X, dtype=int)
    y = np.asarray(y, dtype=float)
    w = np.ones(len(y)) if w is None else np.asarray(w, dtype=float)
    fixed = fixed or {}
    params = init or initial_params(n_levels, positive_hint or {})
    for k, by_z in fixed.items():
        for z, probs in by_z.items():
            params.theta[k][z] = np.asarray(probs, dtype=float)
    history = [objective(params, X, y, w, fixed)]
    for _ in range(max_iter):
        params = m_step(posterior(params, X, y), X, w, n_levels, fixed)
        history.append(objective(params, X, y, w, fixed))
        if abs(history[-1] - history[-2]) < tol:
            break
    return params, posterior(params, X, y), np.array(history)


def likelihood_ratios(params):
    """Per feature and level, p(x | z=1) / p(x | z=0): how much each signal says about transmission."""
    return [th[1] / th[0] for th in params.theta]


def fake_data(n=20000, pi=0.02, n_labelled=0, seed=0):
    """Pairs drawn from the model: 3 binary features and one 4-level score. Returns (X, y, z, n_levels, truth)."""
    rng = np.random.default_rng(seed)
    n_levels = [2, 2, 2, 4]
    truth = [np.array([[0.995, 0.005], [0.4, 0.6]]), np.array([[0.999, 0.001], [0.75, 0.25]]),
             np.array([[0.9, 0.1], [0.3, 0.7]]), np.array([[0.6, 0.3, 0.08, 0.02], [0.05, 0.15, 0.3, 0.5]])]
    z = rng.random(n) < pi
    X = np.column_stack([np.where(z, rng.choice(len(t[1]), n, p=t[1]), rng.choice(len(t[0]), n, p=t[0]))
                         for t in truth])
    y = np.full(n, np.nan)
    if n_labelled:
        idx = rng.choice(n, n_labelled, replace=False)
        y[idx] = z[idx]
    return X, y, z, n_levels, truth
