"""Run from the repo root: python -m pytest test/"""
import numpy as np
import torch

from src.sage.estimate import newton_direction, newton_step, objective
from src.sage.models import SAGE, AdditiveSAGE, background, sparsity
from src.sage.variance import exponential_inv_tau

V = 200


def corpus(etas, n_per=40, length=300, seed=0):
    """Documents drawn from exp(m + eta_k) for each true component; returns (X, y, m)."""
    rng = np.random.default_rng(seed)
    m = np.log(np.sort(rng.dirichlet(np.ones(V) * 0.5))[::-1] + 1e-6)
    X, y = [], []
    for k, eta in enumerate(etas):
        p = np.exp(m + eta)
        p /= p.sum()
        X += [rng.multinomial(length, p) for _ in range(n_per)]
        y += [k] * n_per
    return np.array(X), np.array(y), m


def sparse_eta(words, size=1.5):
    eta = np.zeros(V)
    eta[list(words)] = size
    return eta


def test_newton_direction_matches_a_dense_newton_step():
    """The Sherman-Morrison step equals a dense Newton step; a step never lowers the objective."""
    torch.manual_seed(0)
    c = torch.randint(0, 20, (30,)).double()
    m = torch.log_softmax(torch.randn(30, dtype=torch.float64), 0)
    eta = 0.1 * torch.randn(30, dtype=torch.float64)
    inv_tau = torch.rand(30, dtype=torch.float64) + 0.5
    H = torch.autograd.functional.hessian(lambda e: objective(e, c, m, inv_tau), eta)
    g = torch.autograd.functional.jacobian(lambda e: objective(e, c, m, inv_tau), eta)
    assert torch.allclose(newton_direction(eta, c, m, inv_tau), -torch.linalg.solve(H, g), atol=1e-8)
    assert objective(newton_step(eta, c, m, inv_tau), c, m, inv_tau) >= objective(eta, c, m, inv_tau)


def test_sage_recovers_sparse_deviations_and_classifies():
    X, y, _ = corpus([sparse_eta(range(10, 15)), sparse_eta(range(50, 55)), np.zeros(V)])
    model = SAGE().fit(X, y)
    top0 = set(torch.argsort(model.eta[0], descending=True)[:5].tolist())
    assert top0 == set(range(10, 15))
    assert sparsity(model.eta) > 0.8                     # most deviations exactly (near) zero
    Xt, yt, _ = corpus([sparse_eta(range(10, 15)), sparse_eta(range(50, 55)), np.zeros(V)], n_per=20, seed=1)
    assert (model.predict(Xt) == yt).mean() > 0.9


def test_exponential_prior():
    X, y, _ = corpus([sparse_eta(range(10, 15)), np.zeros(V)])
    model = SAGE(prior='exponential', gamma=1.0).fit(X, y)
    assert set(torch.argsort(model.eta[0], descending=True)[:5].tolist()) == set(range(10, 15))
    inv_tau, a, b = exponential_inv_tau(torch.tensor([0.0, 0.5, 2.0], dtype=torch.float64), gamma=1.0)
    assert torch.all(a > 1) and torch.all(b > 0) and inv_tau[0] > inv_tau[1] > inv_tau[2]   # bigger eta, less shrink


def test_additive_facets():
    """Two facets (language, topic): each document's words come from m + eta_language + eta_topic."""
    lang = [sparse_eta(range(0, 5), 1.0), sparse_eta(range(20, 25), 1.0)]
    topic = [sparse_eta(range(100, 105), 1.5), sparse_eta(range(150, 155), 1.5)]
    etas = [lang[i] + topic[j] for i in range(2) for j in range(2)]
    X, cell, _ = corpus(etas, n_per=30)
    facets = {'lang': cell // 2, 'topic': cell % 2}
    model = AdditiveSAGE().fit(X, facets)
    assert set(torch.argsort(model.component('lang', 1), descending=True)[:5].tolist()) == set(range(20, 25))
    assert set(torch.argsort(model.component('topic', 0), descending=True)[:5].tolist()) == set(range(100, 105))
    assert sparsity(model.eta['lang']) > 0.8 and sparsity(model.eta['topic']) > 0.8
    assert background(X).shape == (V,)
