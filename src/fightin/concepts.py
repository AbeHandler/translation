"""
Shared concepts for comparing word use across languages with Fightin' Words: each word of the source language
(Chinese) is mapped to its nearest pivot-language (English) word in a cross-lingual embedding index when they are
close enough (治理 -> governance); Latin-script words (AI, OpenAI, GPT-4o) are their own lowercased concept in either
language; Chinese words with no close English word stay their own concept. Then both groups count concepts, not
words, so English and Chinese texts share one vocabulary.
"""
import re

import numpy as np

LATIN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9\-\'.]*$')
WORDLIKE = re.compile(r'[A-Za-z一-鿿]')     # at least one letter or Chinese character: no bare numbers or
CHUNK = 2048                                         # punctuation


def normalise(word):
    """The word as counted ('' to leave it out): Latin words lowercased; numbers and punctuation dropped."""
    if not WORDLIKE.search(word):
        return ''
    return word.lower() if LATIN.match(word) else word


def pivot_concepts(index, words, threshold=0.6, source='zh', pivot='en'):
    """{word: (concept, similarity)} for the source-language words: their nearest pivot-language word when the
    cosine is at least threshold, else the word itself (similarity of its best match, for inspection). Latin words
    map to themselves (similarity 1). Words missing from the index map to themselves (similarity 0)."""
    out = {w: (w, 1.0) for w in words if LATIN.match(w)}
    rows = [(w, index.position[(source, w)]) for w in words if w not in out and (source, w) in index.position]
    out.update({w: (w, 0.0) for w in words if w not in out and (source, w) not in index.position})
    targets = np.array([k for k, lang in enumerate(index.langs) if lang == pivot])
    if not rows or not len(targets):
        out.update({w: (w, 0.0) for w, _ in rows})
        return out
    pivots = index.matrix[targets]
    for start in range(0, len(rows), CHUNK):
        chunk = rows[start:start + CHUNK]
        sims = index.matrix[[k for _, k in chunk]] @ pivots.T
        best = sims.argmax(axis=1)
        for (w, _), b, s in zip(chunk, best, sims[np.arange(len(chunk)), best]):
            out[w] = (index.words[targets[b]], float(s)) if s >= threshold else (w, float(s))
    return out


def concept_counts(docs, mapping=None):
    """Counter of concepts over tokenised documents; mapping: {word: (concept, similarity)} (pivot_concepts), or
    None for the pivot language (each word its own concept)."""
    from collections import Counter
    counts = Counter()
    for doc in docs:
        for word in doc:
            word = normalise(word)
            if word:
                counts[mapping[word][0] if mapping and word in mapping else word] += 1
    return counts
