"""
WordLookup: what Fightin' Words needs from word embeddings.
    nearest_words(vector)       the words closest to an embedding (optionally in one language)
    similarity(a, b)            cosine of two words (across languages when the index's space is aligned)
    describe(words, weights)    a bag of words (e.g. a group's top Fightin' words, weighted by their z-scores)
                                averaged into one vector, and that vector's nearest words: what the group's words
                                have in common
"""
import numpy as np

from src.fightin.embeddings.index import unit


class WordLookup:
    def __init__(self, index):
        self.index = index

    def nearest_words(self, vector, k=10, lang=None, exclude=()):
        return self.index.nearest(vector, k=k, lang=lang, exclude=exclude)

    def similarity(self, a, b, lang_a='', lang_b=''):
        va, vb = self.index.vector(a, lang_a), self.index.vector(b, lang_b)
        return None if va is None or vb is None else float(va @ vb)

    def average(self, words, weights=None, lang=''):
        """The weighted mean of the words' unit vectors (words not in the index skipped), as a unit vector; None if
        none is in the index."""
        weights = np.ones(len(words)) if weights is None else np.abs(np.asarray(weights, dtype=float))
        pairs = [(self.index.vector(w, lang), x) for w, x in zip(words, weights)]
        pairs = [(v, x) for v, x in pairs if v is not None]
        if not pairs:
            return None
        return unit(sum(v * x for v, x in pairs))

    def describe(self, words, weights=None, k=10, lang='', target_lang=None):
        """The nearest words to the bag of words' average, leaving the words themselves out."""
        vector = self.average(words, weights, lang)
        if vector is None:
            return []
        return self.nearest_words(vector, k=k, lang=target_lang, exclude=[(lang, w) for w in words])
