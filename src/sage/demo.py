"""
A demo of SAGE after the paper's Figure 2: naive Bayes classification with SAGE components vs a Dirichlet-
multinomial (add-alpha smoothed) model, as the training data shrinks. Synthetic text: 5 classes over 2,000 terms
with a Zipf-like background, each class raising 20 of its own terms (a sparse truth, as SAGE assumes).

Run from the repo root:
    python -m src.sage.demo
"""
import numpy as np
import torch

from src.sage.models import SAGE, as_tensor, sparsity

V, K, LENGTH = 2000, 5, 150


def corpus(n_per, rng, m, etas):
    X, y = [], []
    for k, eta in enumerate(etas):
        p = np.exp(m + eta)
        p /= p.sum()
        X += [rng.multinomial(LENGTH, p) for _ in range(n_per)]
        y += [k] * n_per
    return np.array(X), np.array(y)


def dirichlet_multinomial(X, y, alpha=0.1):
    """log P(w | class) with add-alpha smoothing: the standard naive Bayes."""
    X = as_tensor(X)
    counts = torch.stack([X[torch.as_tensor(y == k)].sum(0) for k in range(K)]) + alpha
    return torch.log(counts / counts.sum(1, keepdim=True))


def main():
    rng = np.random.default_rng(0)
    m = np.log(1 / np.arange(1, V + 1))
    m -= np.log(np.exp(m).sum())
    etas = [np.zeros(V) for _ in range(K)]
    for k in range(K):
        etas[k][rng.choice(V, 20, replace=False)] = 1.5
    Xt, yt = corpus(200, rng, m, etas)
    print(f'{"docs per class":>15} {"SAGE":>6} {"Dirichlet":>9} {"SAGE sparsity":>14}')
    for n in (2, 5, 10, 25, 100):
        X, y = corpus(n, rng, m, etas)
        sage = SAGE().fit(X, y)
        dm = (as_tensor(Xt) @ dirichlet_multinomial(X, y).T).argmax(1).numpy()
        print(f'{n:15d} {(sage.predict(Xt) == yt).mean():6.2f} {(dm == yt).mean():9.2f} {sparsity(sage.eta):14.1%}')


if __name__ == '__main__':
    main()
