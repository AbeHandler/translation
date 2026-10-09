"""
SAGE topic models (Eisenstein, Ahmed & Xing 2011, sec. 4-5): latent topics as sparse log-frequency deviations from
the background, optionally with observed document labels (language x Nvidia ...) as further sparse facets:
    w ~ softmax(m + eta_topic[z] + eta_label[y_d] + eta_label.topic[y_d, z])          z ~ theta_d ~ Dirichlet(alpha)
labels: a label's own vocabulary (eta_label: what's said in Chinese, whatever the topic) and, with interactions, how
a topic is worded under each label (eta_label.topic). Without labels this is SAGE's LDA.
Variational EM: the E-step is LDA's (each document's topic proportions gamma and each word's topic responsibilities),
on the documents' counts; the M-step takes, for every component, a variance update and one Newton step on the
expected counts, the other components held fixed as offsets (src/sage/estimate.py), warm-started, as the paper did.
The first burn_in iterations use a mild Gaussian prior instead: from a random start the topics' deviations are
tiny, and under the sparse priors a tiny deviation is pulled to 0 and stays there (the lock-in the paper warns of).
Topic prevalence by label (the mean topic proportions of a label's documents) says which topics each label's
coverage dwells on: the dimensions along which, e.g., English and Chinese Nvidia coverage differ.
"""
import numpy as np
import torch

from src.sage.estimate import inv_tau_of, newton_step, start
from src.sage.models import DTYPE, background

E_DTYPE = torch.float32     # the E-step's responsibilities (non-zeros x topics) can be large


def _nonzeros(X):
    """(rows, cols, values) of a count matrix's non-zeros (scipy.sparse or dense)."""
    import scipy.sparse as sp
    X = sp.coo_matrix(X)
    return (torch.as_tensor(X.row, dtype=torch.long), torch.as_tensor(X.col, dtype=torch.long),
            torch.as_tensor(X.data, dtype=E_DTYPE))


class SAGETopics:
    def __init__(self, n_topics=20, alpha=0.1, prior='jeffreys', gamma=1.0, em_iters=40, e_iters=20,
                 interactions=True, burn_in=10, restarts=1, seed=0, say=None):
        self.K, self.alpha, self.prior, self.gamma_prior, self.burn_in = n_topics, alpha, prior, gamma, burn_in
        self.em_iters, self.e_iters, self.interactions, self.seed = em_iters, e_iters, interactions, seed
        self.restarts = restarts
        self.say = say or (lambda line: None)

    def log_beta(self):
        """log P(w | label, topic): L x K x V."""
        logits = (self.m + self.eta_topic.unsqueeze(0) + self.eta_label.unsqueeze(1))
        if self.interactions:
            logits = logits + self.eta_inter
        return torch.log_softmax(logits, 2)

    def _e_step(self, rows, cols, vals, y, gamma):
        """Topic proportions gamma (D x K) and the expected counts (L x K x V), LDA's mean-field updates."""
        log_beta = self.log_beta().to(E_DTYPE)[y[rows], :, cols]                  # nnz x K
        for _ in range(self.e_iters):
            elog_theta = torch.digamma(gamma) - torch.digamma(gamma.sum(1, keepdim=True))
            phi = torch.softmax(elog_theta[rows] + log_beta, 1)
            gamma = torch.full_like(gamma, self.alpha).index_add_(0, rows, phi * vals[:, None])
        expected = torch.zeros(self.L, self.K, self.V, dtype=DTYPE)
        flat = (y[rows] * self.K)[:, None] * self.V + torch.arange(self.K)[None, :] * self.V + cols[:, None]
        expected.view(-1).index_add_(0, flat.reshape(-1), (phi * vals[:, None]).reshape(-1).to(DTYPE))
        return gamma, expected

    def _update(self, eta, counts, offsets, key):
        if self._burning:    # a mild Gaussian prior first: under the sparse priors a near-zero start stays at 0
            inv_tau = torch.ones_like(eta)
        else:
            inv_tau, self._state[key] = inv_tau_of(eta, self.prior, self.gamma_prior, self._state.get(key))
        return newton_step(eta, counts, offsets, inv_tau)

    def _m_step(self, C, first):
        """One variance update and Newton step per component; C: expected counts L x K x V."""
        for k in range(self.K):                     # topic k: one group per label
            o = (self.m + self.eta_label + (self.eta_inter[:, k] if self.interactions else 0))
            eta = start(C[:, k], o) if first else self.eta_topic[k]
            self.eta_topic[k] = self._update(eta, C[:, k], o, ('t', k))
        if self.L > 1:
            for j in range(self.L):                 # label j: one group per topic
                o = (self.m + self.eta_topic + (self.eta_inter[j] if self.interactions else 0))
                self.eta_label[j] = self._update(self.eta_label[j], C[j], o, ('l', j))
            if self.interactions:
                for j in range(self.L):
                    for k in range(self.K):
                        o = self.m + self.eta_topic[k] + self.eta_label[j]
                        self.eta_inter[j, k] = self._update(self.eta_inter[j, k], C[j, k], o, ('i', j, k))

    def fit(self, X, labels=None):
        """X: documents x V counts (scipy.sparse or dense); labels: one per document (None: no label facets). With
        restarts > 1, fits from that many random starts and keeps the one with the highest likelihood (EM finds
        local optima)."""
        best = None
        for r in range(self.restarts):
            self.say(f'start {r + 1}/{self.restarts}')
            self._fit_once(X, labels, self.seed + r)
            self.say(f'  log-likelihood per token {self.loglik:.4f}')
            if best is None or self.loglik > best['loglik']:
                best = dict(self.__dict__)
        self.__dict__.update(best)
        return self

    def _fit_once(self, X, labels, seed):
        labels = np.zeros(X.shape[0], dtype=int) if labels is None else np.asarray(labels)
        self.levels, y = np.unique(labels, return_inverse=True)
        y = torch.as_tensor(y.reshape(-1), dtype=torch.long)
        self.L, self.V, D = len(self.levels), X.shape[1], X.shape[0]
        self.m = background(X)
        self.eta_topic = torch.zeros(self.K, self.V, dtype=DTYPE)
        self.eta_label = torch.zeros(self.L, self.V, dtype=DTYPE)
        self.eta_inter = torch.zeros(self.L, self.K, self.V, dtype=DTYPE)
        self._state = {}
        rows, cols, vals = _nonzeros(X)
        torch.manual_seed(seed)        # a random start: each document's words get the document's own random topic mix
        doc_mix = torch.distributions.Dirichlet(torch.full((self.K,), 0.1)).sample((D,)).to(E_DTYPE)
        phi = doc_mix[rows]
        C = torch.zeros(self.L, self.K, self.V, dtype=DTYPE)
        flat = (y[rows] * self.K)[:, None] * self.V + torch.arange(self.K)[None, :] * self.V + cols[:, None]
        C.view(-1).index_add_(0, flat.reshape(-1), (phi * vals[:, None]).reshape(-1).to(DTYPE))
        self._burning = True
        self._m_step(C, first=True)
        gamma = torch.full((D, self.K), self.alpha, dtype=E_DTYPE).index_add_(0, rows, phi * vals[:, None])
        n_tokens = float(vals.sum())
        for it in range(self.em_iters):
            self._burning = it < self.burn_in
            gamma, C = self._e_step(rows, cols, vals, y, gamma)
            self._m_step(C, first=False)
            if it % 5 == 4 or it == self.em_iters - 1:
                per_token = self._loglik(rows, cols, vals, y, gamma) / n_tokens
                self.say(f'  EM {it + 1}/{self.em_iters}: log-likelihood per token {per_token:.4f}')
        self.gamma = gamma
        self.labels = y
        self.loglik = self._loglik(rows, cols, vals, y, gamma) / n_tokens

    def _loglik(self, rows, cols, vals, y, gamma):
        theta = gamma / gamma.sum(1, keepdim=True)
        beta = self.log_beta().to(E_DTYPE).exp()[y[rows], :, cols]
        return float((vals * torch.log((theta[rows] * beta).sum(1) + 1e-30)).sum())

    def doc_topics(self):
        """D x K topic proportions."""
        return (self.gamma / self.gamma.sum(1, keepdim=True)).numpy()

    def prevalence(self):
        """L x K: the mean topic proportions of each label's documents."""
        theta = self.doc_topics()
        y = self.labels.numpy()
        return np.stack([theta[y == j].mean(0) for j in range(self.L)])
