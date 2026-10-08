"""
SAGE models over term-count matrices (documents x V; numpy, scipy.sparse or torch):
    background(X)     m: the log term frequencies of the whole collection (fixed; sec. 3)
    SAGE              one sparse component per class: P(w | y) ~ exp(m + eta_y) (eq. 1). fit(X, y) estimates each
                      component by the paper's Newton procedure; log_likelihood / predict make it the naive Bayes
                      classifier of Application 1
    AdditiveSAGE      several facets of observed labels per document (language, topic, outlet ...), their
                      components added in log space: P(w | labels) ~ exp(m + sum_f eta_f[label_f]) (sec. 5),
                      with no switching variables. Estimated jointly (L-BFGS), alternating with the variances
    top_terms         a component's largest positive (or negative) deviations
"""
import numpy as np
import torch

from src.sage.estimate import estimate_component
from src.sage.variance import exponential_inv_tau, jeffreys_inv_tau

DTYPE = torch.float64
ZERO = 1e-4         # |eta| below this counts as zero (the Jeffreys prior drives unsupported deviations to 0)


def as_tensor(X):
    """A dense float64 tensor of term counts."""
    if hasattr(X, 'toarray'):
        X = X.toarray()
    return torch.as_tensor(np.asarray(X), dtype=DTYPE)


def background(X, smooth=1.0):
    """m: log of each term's share of all counts (smoothed, so no term is -inf)."""
    total = as_tensor(X).sum(0) + smooth
    return torch.log(total / total.sum())


def sparsity(eta):
    return float((eta.abs() < ZERO).double().mean())


class SAGE:
    def __init__(self, prior='jeffreys', gamma=1.0, iters=100):
        self.prior, self.gamma, self.iters = prior, gamma, iters

    def fit(self, X, y, m=None):
        """One component per class from the documents' counts X (n x V) and labels y (n)."""
        X, y = as_tensor(X), np.asarray(y)
        self.classes = np.unique(y)
        self.m = background(X) if m is None else torch.as_tensor(m, dtype=DTYPE)
        self.eta = torch.stack([estimate_component(X[torch.as_tensor(y == k)].sum(0), self.m, self.prior,
                                                   self.gamma, self.iters) for k in self.classes])
        return self

    def log_beta(self):
        """log P(w | class): K x V."""
        return torch.log_softmax(self.eta + self.m, 1)

    def log_likelihood(self, X):
        """log P(document | class), n x K (the multinomial coefficient left out)."""
        return as_tensor(X) @ self.log_beta().T

    def predict(self, X):
        return self.classes[self.log_likelihood(X).argmax(1).numpy()]


class AdditiveSAGE:
    def __init__(self, prior='jeffreys', gamma=1.0, rounds=30, lbfgs_iters=50):
        self.prior, self.gamma, self.rounds, self.lbfgs_iters = prior, gamma, rounds, lbfgs_iters

    def fit(self, X, facets, m=None):
        """facets: {name: labels (n)}. Documents with the same labels in every facet are pooled (the model
        only sees their summed counts), then all components are fitted jointly."""
        X = as_tensor(X)
        self.m = background(X) if m is None else torch.as_tensor(m, dtype=DTYPE)
        self.levels = {f: np.unique(np.asarray(v)) for f, v in facets.items()}
        codes = np.stack([np.searchsorted(self.levels[f], np.asarray(v)) for f, v in facets.items()], 1)
        groups, which = np.unique(codes, axis=0, return_inverse=True)
        which = torch.as_tensor(which.reshape(-1))
        counts = torch.zeros(len(groups), X.shape[1], dtype=DTYPE).index_add_(0, which, X)
        groups = torch.as_tensor(groups)
        V = X.shape[1]
        self.eta = {f: (0.01 * torch.randn(len(lv), V, dtype=DTYPE, generator=torch.Generator().manual_seed(0)))
                    .requires_grad_() for f, lv in self.levels.items()}
        names = list(self.levels)
        inv_tau = {f: torch.ones_like(e) for f, e in self.eta.items()}
        a = {f: None for f in names}
        for _ in range(self.rounds):
            opt = torch.optim.LBFGS(list(self.eta.values()), max_iter=self.lbfgs_iters, line_search_fn='strong_wolfe')

            def closure():
                opt.zero_grad()
                logits = self.m + sum(self.eta[f][groups[:, k]] for k, f in enumerate(names))
                loglik = (counts * torch.log_softmax(logits, 1)).sum()
                penalty = sum(0.5 * (inv_tau[f] * self.eta[f] ** 2).sum() for f in names)
                loss = -(loglik - penalty) / counts.sum()
                loss.backward()
                return loss
            opt.step(closure)
            with torch.no_grad():
                for f in names:
                    if self.prior == 'jeffreys':
                        inv_tau[f] = jeffreys_inv_tau(self.eta[f])
                    else:
                        inv_tau[f], a[f], _ = exponential_inv_tau(self.eta[f], self.gamma, a[f])
        self.eta = {f: e.detach() for f, e in self.eta.items()}
        return self

    def component(self, facet, label):
        return self.eta[facet][int(np.searchsorted(self.levels[facet], label))]

    def log_beta(self, labels):
        """log P(w | labels): labels {facet: label}."""
        return torch.log_softmax(self.m + sum(self.component(f, v) for f, v in labels.items()), 0)


def top_terms(eta, vocab, k=20, negative=False):
    """[(term, deviation)] of the k largest (or most negative) deviations."""
    order = torch.argsort(eta, descending=not negative)[:k]
    return [(vocab[i], float(eta[i])) for i in order]
