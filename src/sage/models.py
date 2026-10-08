"""
SAGE models over term-count matrices (documents x V; numpy, scipy.sparse or torch):
    background(X)     m: the log term frequencies of the whole collection (fixed; sec. 3)
    SAGE              one sparse component per class: P(w | y) ~ exp(m + eta_y) (eq. 1). fit(X, y) estimates each
                      component by the paper's Newton procedure; log_likelihood / predict make it the naive Bayes
                      classifier of Application 1
    AdditiveSAGE      several facets of observed labels per document (language, topic, outlet ...), their
                      components added in log space: P(w | labels) ~ exp(m + sum_f eta_f[label_f]) (sec. 5),
                      with no switching variables. Coordinate ascent: the same Newton steps, other facets as
                      offsets
    top_terms         a component's largest positive (or negative) deviations
"""
import numpy as np
import torch

from src.sage.estimate import estimate_component, inv_tau_of, newton_step

DTYPE = torch.float64
ZERO = 1e-4         # |eta| below this counts as zero (the Jeffreys prior drives unsupported deviations to 0)


def as_tensor(X):
    """A dense float64 tensor of term counts."""
    if hasattr(X, 'toarray'):
        X = X.toarray()
    return torch.as_tensor(np.asarray(X), dtype=DTYPE)


def group_sums(X, which, n_groups):
    """The summed counts of each group's documents (G x V tensor); which: each document's group (n). X may be a
    scipy.sparse matrix: documents are pooled before anything is dense."""
    if hasattr(X, 'tocsr'):
        import scipy.sparse as sp
        member = sp.csr_matrix((np.ones(len(which)), (np.asarray(which), np.arange(len(which)))),
                               shape=(n_groups, X.shape[0]))
        return as_tensor(member @ X)
    X = as_tensor(X)
    return torch.zeros(n_groups, X.shape[1], dtype=DTYPE).index_add_(0, torch.as_tensor(np.asarray(which)), X)


def background(X, smooth=1.0):
    """m: log of each term's share of all counts (smoothed, so no term is -inf)."""
    total = group_sums(X, np.zeros(X.shape[0], dtype=int), 1)[0] + smooth
    return torch.log(total / total.sum())


def sparsity(eta):
    return float((eta.abs() < ZERO).double().mean())


class SAGE:
    def __init__(self, prior='jeffreys', gamma=1.0, iters=100):
        self.prior, self.gamma, self.iters = prior, gamma, iters

    def fit(self, X, y, m=None):
        """One component per class from the documents' counts X (n x V) and labels y (n)."""
        self.classes, which = np.unique(np.asarray(y), return_inverse=True)
        self.m = background(X) if m is None else torch.as_tensor(m, dtype=DTYPE)
        sums = group_sums(X, which.reshape(-1), len(self.classes))
        self.eta = torch.stack([estimate_component(c, self.m, self.prior, self.gamma, self.iters) for c in sums])
        return self

    def log_beta(self):
        """log P(w | class): K x V."""
        return torch.log_softmax(self.eta + self.m, 1)

    def log_likelihood(self, X):
        """log P(document | class), n x K (the multinomial coefficient left out)."""
        if hasattr(X, 'tocsr'):
            return torch.as_tensor(X @ self.log_beta().T.numpy())
        return as_tensor(X) @ self.log_beta().T

    def predict(self, X):
        return self.classes[self.log_likelihood(X).argmax(1).numpy()]


class AdditiveSAGE:
    def __init__(self, prior='jeffreys', gamma=1.0, rounds=50, tol=1e-5):
        self.prior, self.gamma, self.rounds, self.tol = prior, gamma, rounds, tol

    def fit(self, X, facets, m=None):
        """facets: {name: labels (n)}. Documents with the same labels in every facet are pooled (the model only
        sees their summed counts). Coordinate ascent (sec. 5): each component in turn takes a variance update and
        a Newton step, the other facets' components held fixed as offsets."""
        self.m = background(X) if m is None else torch.as_tensor(m, dtype=DTYPE)
        self.levels = {f: np.unique(np.asarray(v)) for f, v in facets.items()}
        names = list(self.levels)
        codes = np.stack([np.searchsorted(self.levels[f], np.asarray(v)) for f, v in facets.items()], 1)
        groups, which = np.unique(codes, axis=0, return_inverse=True)
        counts = group_sums(X, which.reshape(-1), len(groups))
        groups = torch.as_tensor(groups)
        V = counts.shape[1]
        self.eta = {f: torch.zeros(len(lv), V, dtype=DTYPE) for f, lv in self.levels.items()}
        state = {(f, k): None for f in names for k in range(len(self.levels[f]))}

        def offsets(f, rows):
            return self.m + sum(self.eta[h][groups[rows, j]] for j, h in enumerate(names) if h != f)
        for f in names:                      # start: each component's smoothed ML deviation, given the background
            for k in range(len(self.levels[f])):
                rows = groups[:, names.index(f)] == k
                self.eta[f][k] = estimate_component(counts[rows], self.m.expand(int(rows.sum()), V), iters=0)
        for _ in range(self.rounds):
            moved = 0.0
            for j, f in enumerate(names):
                for k in range(len(self.levels[f])):
                    rows = groups[:, j] == k
                    eta = self.eta[f][k]
                    inv_tau, state[f, k] = inv_tau_of(eta, self.prior, self.gamma, state[f, k])
                    new = newton_step(eta, counts[rows], offsets(f, rows), inv_tau)
                    moved = max(moved, float(torch.max(torch.abs(new - eta))))
                    self.eta[f][k] = new
            if moved < self.tol:
                break
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
