"""Matching a source sentence to its closest target sentences, by a multilingual sentence encoder (LaBSE in
practice; injected, so tests use a fake)."""
import numpy as np


class SentenceMatcher:
    def __init__(self, encode, min_score=0.6, top_k=1):
        self.encode = encode           # list[str] -> (n, d) unit vectors
        self.min_score = min_score
        self.top_k = top_k

    def match(self, source_sentence, target_sentences):
        """[(target sentence, score)] best first, at least min_score."""
        if not target_sentences:
            return []
        src = self.encode([source_sentence.text])[0]
        sims = self.encode([s.text for s in target_sentences]) @ src
        best = np.argsort(-sims)[:self.top_k]
        return [(target_sentences[i], float(sims[i])) for i in best if sims[i] >= self.min_score]
