"""
Documents to SAGE inputs: a sparse document x term count matrix and its vocabulary, with the units and cleaning of
Fightin' Words (src/fightin): words or phrases (src/fightin/units.py), Chinese names in English
(src/fightin/renderings.py), syndicated copies counted once (src/fightin/contexts.py dedupe), only units used at
min_outlets+ outlets (one site's boilerplate left out).
"""
from collections import Counter

import numpy as np
import scipy.sparse as sp

from src.dispersion.tokens import tokens
from src.fightin.contexts import dedupe
from src.fightin.units import units, widespread


def doc_units(docs, ns=(2, 3), min_outlets=2, renderings=None, stop=frozenset()):
    """(each document's units, the documents kept: syndicated copies dropped). Units used at fewer than min_outlets
    outlets are left out."""
    docs, _ = dedupe(docs)
    docs = docs.reset_index(drop=True)
    found = []
    for text, lang in zip(docs['text'], docs['lang']):
        if lang == 'zh' and renderings is not None:
            text = renderings.apply(text)
        found.append(units([t for t, _, _ in tokens(text, lang)], lang, ns, stop))
    return widespread(found, docs['outlet'], min_outlets), docs


def vocabulary(found, min_df=5, max_vocab=30000):
    """The units in min_df+ documents, most widespread first, at most max_vocab."""
    df = Counter(u for f in found for u in set(f))
    return [u for u, n in df.most_common(max_vocab) if n >= min_df]


def count_matrix(found, vocab):
    """csr documents x V of the units' counts (units outside vocab ignored)."""
    column = {u: k for k, u in enumerate(vocab)}
    rows, cols, vals = [], [], []
    for d, f in enumerate(found):
        for u, n in Counter(u for u in f if u in column).items():
            rows.append(d)
            cols.append(column[u])
            vals.append(n)
    return sp.csr_matrix((np.array(vals, dtype=float), (rows, cols)), shape=(len(found), len(vocab)))


def featurise(docs, ns=(2, 3), min_df=5, max_vocab=30000, min_outlets=2, renderings=None, stop=frozenset()):
    """(X: csr documents x V, vocab: V terms, docs: the documents kept, row-aligned with X). docs: a DataFrame with
    lang, outlet, title, text (one language or several: units of different languages simply don't overlap)."""
    found, docs = doc_units(docs, ns, min_outlets, renderings, stop)
    vocab = vocabulary(found, min_df, max_vocab)
    X = count_matrix(found, vocab)
    keep = np.asarray(X.sum(1)).ravel() > 0
    return X[keep], vocab, docs[keep].reset_index(drop=True)
