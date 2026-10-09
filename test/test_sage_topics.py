"""Run from the repo root: python -m pytest test/"""
import numpy as np
import torch

from src.sage.models import sparsity
from src.sage.topics import SAGETopics

V = 300


def corpus(seed=0, n=240, length=120):
    """Documents mixing 3 sparse topics (each raising its own 10 words), half labelled 'b' (raising 5 more words)."""
    rng = np.random.default_rng(seed)
    m = np.log(1 / np.arange(1, V + 1))
    topics = np.zeros((3, V))
    for k in range(3):
        topics[k, 100 + 30 * k: 110 + 30 * k] = 4.0
    label = np.zeros((2, V))
    label[1, 250:255] = 2.0
    X, labels = [], []
    for d in range(n):
        y = d % 2
        theta = rng.dirichlet(np.full(3, 0.3))
        counts = np.zeros(V)
        for z in rng.choice(3, length, p=theta):
            p = np.exp(m + topics[z] + label[y])
            counts[rng.choice(V, p=p / p.sum())] += 1
        X.append(counts)
        labels.append('ab'[y])
    return np.array(X), np.array(labels)


def test_topics_and_label_facet_recovered():
    X, labels = corpus()
    model = SAGETopics(n_topics=3, em_iters=40, burn_in=15, interactions=False, restarts=3).fit(X, labels)
    found = [set(torch.argsort(model.eta_topic[k], descending=True)[:10].tolist()) for k in range(3)]
    planted = [set(range(100 + 30 * k, 110 + 30 * k)) for k in range(3)]
    assert all(max(len(f & p) for f in found) >= 7 for p in planted)        # each planted topic found
    b = model.eta_label[list(model.levels).index('b')]
    assert set(torch.argsort(b, descending=True)[:5].tolist()) == set(range(250, 255))
    assert sparsity(model.eta_topic) > 0.5
    prevalence = model.prevalence()
    assert prevalence.shape == (2, 3) and np.allclose(prevalence.sum(1), 1, atol=1e-4)


def test_without_labels_and_with_interactions_runs():
    X, labels = corpus(n=60)
    assert SAGETopics(n_topics=3, em_iters=3).fit(X).eta_topic.shape == (3, V)
    model = SAGETopics(n_topics=3, em_iters=3, interactions=True).fit(X, labels)
    assert model.eta_inter.shape == (2, 3, V) and model.doc_topics().shape == (60, 3)
