"""
Estimating one SAGE component eta (a V-vector of log-frequency deviations) by Newton steps (sec. 3.1, 5). The
component is shared by one or more groups of documents g, each with its summed counts c_g and an offset o_g (the
background m, plus the other facets' components for that group, sec. 5); it maximises
    l(eta) = sum_g [c_g.eta - C_g log sum_i exp(eta_i + o_gi)] - eta' diag(<1/tau>) eta / 2           (eq. 3)
With one group (o = m) this is the paper's eq. 3 exactly. The Hessian is diagonal plus rank one,
H = C beta beta' - diag(C beta + <1/tau>) (eq. 5), with C beta = sum_g C_g beta_g for several groups (the paper's
substitution, sec. 5), so a step costs O(V) by Sherman-Morrison (eq. 6). Alternated with the variance updates
(src/sage/variance.py).
"""
import torch

from src.sage.variance import exponential_inv_tau, jeffreys_inv_tau


def _2d(x):
    return x if x.dim() == 2 else x.unsqueeze(0)


def objective(eta, c, o, inv_tau):
    """c, o: V (one group) or G x V."""
    c, o = _2d(c), _2d(o)
    return (c @ eta).sum() - (c.sum(1) * torch.logsumexp(eta + o, 1)).sum() - 0.5 * (inv_tau * eta * eta).sum()


def newton_direction(eta, c, o, inv_tau):
    """-H^-1 g (eqs. 4-6) in O(G V)."""
    c, o = _2d(c), _2d(o)
    expected = (c.sum(1, keepdim=True) * torch.softmax(eta + o, 1)).sum(0)     # sum_g C_g beta_g
    C = c.sum()
    beta = expected / C
    g = c.sum(0) - expected - inv_tau * eta                                     # eq. 4
    d_inv = 1.0 / (expected + inv_tau)                                          # -H = D - C beta beta'
    dg, db = d_inv * g, d_inv * beta
    return dg + C * db * (beta @ dg) / (1 - C * (beta @ db))                    # Sherman-Morrison (eq. 6)


def newton_step(eta, c, o, inv_tau):
    """eta after one Newton step, halved until the objective doesn't fall."""
    step = newton_direction(eta, c, o, inv_tau)
    before, size = objective(eta, c, o, inv_tau), 1.0
    for _ in range(30):
        new = eta + size * step
        if objective(new, c, o, inv_tau) >= before:
            return new
        size /= 2
    return eta


def inv_tau_of(eta, prior, gamma, a):
    """(<1/tau>, a) for the prior; a: the Exponential prior's variational state (None for Jeffreys)."""
    if prior == 'jeffreys':
        return jeffreys_inv_tau(eta), None
    inv_tau, a, _ = exponential_inv_tau(eta, gamma, a)
    return inv_tau, a


def start(c, o):
    """The smoothed maximum-likelihood deviation (under the Jeffreys prior an eta at 0 stays at 0)."""
    c, o = _2d(c), _2d(o)
    counts = c.sum(0)
    return torch.log((counts + 0.5) / (counts.sum() + 0.5 * len(counts))) - torch.logsumexp(o, 0) + \
        torch.log(torch.tensor(float(len(o)), dtype=o.dtype))


def estimate_component(c, m, prior='jeffreys', gamma=1.0, iters=100, tol=1e-6, eta=None):
    """The MAP eta for counts c against offsets m (V, or G x V for several groups), alternating <1/tau> updates
    and a Newton step (the paper found one Newton step per variance update enough, with a warm start)."""
    eta = start(c, m) if eta is None else eta
    a = None
    for _ in range(iters):
        inv_tau, a = inv_tau_of(eta, prior, gamma, a)
        new = newton_step(eta, c, m, inv_tau)
        if torch.max(torch.abs(new - eta)) < tol:
            return new
        eta = new
    return eta
