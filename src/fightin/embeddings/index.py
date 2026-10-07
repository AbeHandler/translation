"""
VectorIndex: words, their unit vectors, and an optional language tag per word; nearest neighbours by cosine,
brute force in chunks (a matrix product: fast enough for a million words, no extra dependencies). Several
languages can share one index when their vectors share a space (fastText's aligned vectors).
"""
import numpy as np

CHUNK = 200_000   # rows compared at a time, so memory stays bounded


def unit(vectors):
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class VectorIndex:
    def __init__(self, dim=None):
        self.dim = dim
        self.words, self.langs, self._chunks = [], [], []
        self._matrix = None
        self.position = {}

    def add(self, words, vectors, lang=''):
        """Add words with their vectors (normalised here); a word already in the index for the language is kept."""
        vectors = unit(vectors)
        if self.dim is None:
            self.dim = vectors.shape[1]
        if vectors.shape[1] != self.dim:
            raise ValueError(f'vectors have {vectors.shape[1]} dimensions, the index {self.dim}')
        keep = [k for k, w in enumerate(words) if (lang, w) not in self.position]
        for k in keep:
            self.position[(lang, words[k])] = len(self.words)
            self.words.append(words[k])
            self.langs.append(lang)
        self._chunks.append(vectors[keep])
        self._matrix = None
        return len(keep)

    @property
    def matrix(self):
        if self._matrix is None:
            self._matrix = np.vstack(self._chunks) if self._chunks else np.zeros((0, self.dim or 0), np.float32)
            self._chunks = [self._matrix]
        return self._matrix

    def __len__(self):
        return len(self.words)

    def vector(self, word, lang=''):
        """The word's unit vector, or None if it isn't in the index."""
        k = self.position.get((lang, word))
        return None if k is None else self.matrix[k]

    def nearest(self, vector, k=10, lang=None, exclude=()):
        """[(word, lang, cosine)] of the k words closest to the vector, best first; lang: only that language's."""
        query = unit(vector)
        allowed = None if lang is None else np.array([tag == lang for tag in self.langs])
        skip = {self.position[x] for x in exclude if x in self.position}
        best = []
        for start in range(0, len(self.words), CHUNK):
            sims = self.matrix[start:start + CHUNK] @ query
            if allowed is not None:
                sims = np.where(allowed[start:start + CHUNK], sims, -np.inf)
            top = np.argpartition(-sims, min(k + len(skip), len(sims) - 1))[:k + len(skip)]
            best += [(float(sims[i]), start + i) for i in top if start + i not in skip and sims[i] > -np.inf]
        best.sort(reverse=True)
        return [(self.words[i], self.langs[i], s) for s, i in best[:k]]

    def save(self, path):
        np.savez_compressed(path, matrix=self.matrix, words=np.array(self.words, dtype=object),
                            langs=np.array(self.langs, dtype=object))

    @classmethod
    def load(cls, path):
        data = np.load(path, allow_pickle=True)
        index = cls(data['matrix'].shape[1])
        by_lang = {}
        for k, (w, lang) in enumerate(zip(data['words'], data['langs'])):
            by_lang.setdefault(lang, []).append(k)
        for lang, rows in by_lang.items():
            index.add([str(data['words'][k]) for k in rows], data['matrix'][rows], lang=str(lang))
        return index
