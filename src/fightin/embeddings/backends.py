"""
Ways to fill a VectorIndex, each giving (words, vectors):
    read_vec       fastText's .vec text format (a "count dim" header, then "word v1 ... vd" per line), in file order
                   (most frequent first), at most max_words; pure Python. Pretrained: cc.<lang>.300.vec (Common
                   Crawl, one space per language), or wiki.<lang>.align.vec (aligned: English and Chinese in one
                   space, so 治理 sits near "governance")
    from_encoder   any encoder (a callable: list of words -> vectors), e.g. LaBSE or bge via sentence-transformers
    from_dict      a {word: vector} mapping
"""
import gzip

import numpy as np


def read_vec(path, max_words=200_000, keep=None):
    """(words, vectors) from a fastText .vec(.gz) file: the first max_words, or only those for which keep(word)."""
    opener = gzip.open if str(path).endswith('.gz') else open
    words, rows = [], []
    with opener(path, 'rt', encoding='utf-8', errors='replace') as f:
        first = f.readline().split()
        dim = int(first[1]) if len(first) == 2 else len(first) - 1
        if len(first) != 2:                      # no header: the first line is a vector
            words.append(first[0])
            rows.append(np.array(first[1:], dtype=np.float32))
        for line in f:
            if len(words) >= max_words:
                break
            parts = line.rstrip('\n').rsplit(' ', dim)
            if len(parts) != dim + 1 or (keep and not keep(parts[0])):
                continue
            words.append(parts[0])
            rows.append(np.array(parts[1:], dtype=np.float32))
    return words, np.vstack(rows) if rows else np.zeros((0, dim), np.float32)


def from_encoder(words, encode, batch=1024):
    """(words, vectors) of a word list by an encoder (list of str -> array)."""
    words = list(dict.fromkeys(words))
    vectors = [np.asarray(encode(words[k:k + batch]), dtype=np.float32) for k in range(0, len(words), batch)]
    return words, np.vstack(vectors) if vectors else np.zeros((0, 0), np.float32)


def from_dict(mapping):
    words = list(mapping)
    return words, np.array([mapping[w] for w in words], dtype=np.float32)
