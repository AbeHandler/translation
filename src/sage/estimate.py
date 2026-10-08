"""
Estimating one SAGE component eta (a V-vector of log-frequency deviations from the background m) from its term
counts c (sec. 3.1): maximise
    l(eta) = c.eta - C log sum_i exp(eta_i + m_i) - eta' diag(<1/tau>) eta / 2           (eq. 3)
by Newton steps. The Hessian is diagonal plus rank one, H = C beta beta' - diag(C beta + <1/tau>) (eq. 5), so a
step costs O(V) by Sherman-Morrison (eq. 6). Alternated with the variance updates (src/sage/variance.py).
"""
import torch

from src.sage.variance import exponential_inv_tau, jeffreys_inv_tau


def objective(eta, c, m, inv_tau):
    C = c.sum()
    return c @ eta - C * torch.logsumexp(eta + m, 0) - 0.5 * (inv_tau * eta * eta).sum()


def newton_direction(eta, c, m, inv_tau):
    """-H^-1 g (eqs. 4-6) in O(V)."""
    C = c.sum()
    beta = torch.softmax(eta + m, 0)
    g = c - C * beta - inv_tau * eta                               # eq. 4
    d_inv = 1.0 / (C * beta + inv_tau)                             # -H = D - C beta beta', D diagonal
    dg, db = d_inv * g, d_inv * beta
    return dg + C * db * (beta @ dg) / (1 - C * (beta @ db))       # (D - C beta beta')^-1 g, Sherman-Morrison


def newton_step(eta, c, m, inv_tau):
    """eta after one Newton step, halved until the objective doesn't fall."""
    step = newton_direction(eta, c, m, inv_tau)
    before, size = objective(eta, c, m, inv_tau), 1.0
    for _ in range(30):
        new = eta + size * step
        if objective(new, c, m, inv_tau) >= before:
            return new
        size /= 2
    return eta


def estimate_component(c, m, prior='jeffreys', gamma=1.0, iters=100, tol=1e-6, eta=None):
    """The MAP eta for counts c (V) against background m (V), alternating <1/tau> updates and a Newton step
    (the paper found one Newton step per variance update enough, with a warm start). eta: a start (default: the
    smoothed maximum-likelihood deviation, since under the Jeffreys prior an eta at 0 stays at 0)."""
    if eta is None:
        eta = torch.log((c + 0.5) / (c.sum() + 0.5 * len(c))) - m
    a = None
    for _ in range(iters):
        if prior == 'jeffreys':
            inv_tau = jeffreys_inv_tau(eta)
        else:
            inv_tau, a, _ = exponential_inv_tau(eta, gamma, a)
        new = newton_step(eta, c, m, inv_tau)
        if torch.max(torch.abs(new - eta)) < tol:
            return new
        eta = new
    return eta
