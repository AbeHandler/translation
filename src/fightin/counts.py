"""Word counts for two groups (i, j) over one shared vocabulary, the input of every measure (the paper's y_kw^(i),
y_kw^(j)); and an optional background (the prior's y_kw: e.g. all topics, or all groups)."""
from collections import Counter
from dataclasses import dataclass

import numpy as np


@dataclass
class GroupCounts:
    words: list            # the vocabulary, W words
    i: np.ndarray          # counts of each word in group i
    j: np.ndarray          # in group j
    background: np.ndarray = None   # counts in a background corpus (for the informative prior); None: i + j


def count(docs_i, docs_j, background_docs=None, min_count=1):
    """GroupCounts from tokenised documents (lists of words) of each group; words used fewer than min_count times
    in all are left out (the paper keeps all; a floor only keeps the vocabulary manageable)."""
    ci, cj = Counter(w for d in docs_i for w in d), Counter(w for d in docs_j for w in d)
    cb = Counter(w for d in background_docs for w in d) if background_docs is not None else None
    total = ci + cj + (cb or Counter())
    words = sorted(w for w, n in total.items() if n >= min_count)
    bg = np.array([cb[w] for w in words], dtype=float) if cb is not None else None
    return GroupCounts(words, np.array([ci[w] for w in words], dtype=float),
                       np.array([cj[w] for w in words], dtype=float), bg)
