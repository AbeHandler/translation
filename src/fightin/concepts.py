"""
Shared concepts for comparing word use across languages with Fightin' Words: each word of the source language
(Chinese) is mapped to its nearest pivot-language (English) word in a cross-lingual embedding index when they are
close enough (治理 -> governance); Latin-script words (AI, OpenAI, GPT-4o) are their own lowercased concept in either
language; Chinese words with no close English word stay their own concept. Then both groups count concepts, not
words, so English and Chinese texts share one vocabulary.

Two leaks to keep out of the comparison: stray words of the other language (Chinese characters on English pages,
"of" or "is" inside Chinese pages), and function words, which have no counterpart across languages (该 -> the,
以及 -> and). So English documents count only Latin-script words, and concepts that are stopwords (in either
language: a Chinese word mapped to "the" is dropped too) are left out. In Chinese documents, Latin-script words
count only as names and acronyms (any capital: AI, OpenAI, GPT-4o, Google): all-lowercase ones ("new", "data") are
running English text quoted in the page, not Chinese usage.
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


def concept_counts(docs, mapping=None, stopwords=frozenset()):
    """Counter of concepts over tokenised documents. mapping: {word: (concept, similarity)} (pivot_concepts) for
    the source language, whose documents then count Latin-script words only when they have a capital (names,
    acronyms); None for the pivot language, whose documents count only Latin-script words (each its own concept).
    Concepts in stopwords are left out."""
    from collections import Counter
    counts = Counter()
    for doc in docs:
        for raw in doc:
            word = normalise(raw)
            quoted_english = mapping is not None and LATIN.match(word) and raw.islower()
            if not word or (mapping is None and not LATIN.match(word)) or quoted_english:
                continue
            concept = mapping[word][0] if mapping and word in mapping else word
            if concept not in stopwords:
                counts[concept] += 1
    return counts


def read_stopwords(path):
    """The words of a stopword file: one per line, # comments."""
    with open(path, encoding='utf-8') as f:
        return frozenset(line.strip() for line in f if line.strip() and not line.startswith('#'))
