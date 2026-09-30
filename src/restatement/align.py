"""
Aligning a citing paragraph with the Chinese page: each English sentence's closest Chinese sentences by cosine
similarity of LaBSE embeddings (trained on translation pairs, so a translation scores ~0.85+), and a first
label from the paragraph's best score. The cut-offs are starting points, to be checked on real pairs.
"""
import numpy as np

MODEL = 'sentence-transformers/LaBSE'
TRANSLATION_MIN = 0.80  # a sentence and its translation
PARAPHRASE_MIN = 0.60   # same content, reworded or partly
TOP_K = 3


def label(score):
    if score >= TRANSLATION_MIN:
        return 'translation'
    if score >= PARAPHRASE_MIN:
        return 'paraphrase'
    return 'neither'


class Aligner:
    def __init__(self, model):
        self.model = model  # a SentenceTransformer

    def embed(self, sentences):
        return self.model.encode(sentences, normalize_embeddings=True, batch_size=32, convert_to_numpy=True)

    def align(self, en_sentences, zh_sentences, top_k=TOP_K):
        """[{en, matches: [{zh, score}]}] best first, and the best score over all of them (0 if either is empty)."""
        if not en_sentences or not zh_sentences:
            return [], 0.0
        scores = self.embed(en_sentences) @ self.embed(zh_sentences).T
        rows = []
        for i, en in enumerate(en_sentences):
            best = np.argsort(-scores[i])[:top_k]
            rows.append({'en': en, 'matches': [{'zh': zh_sentences[j], 'score': round(float(scores[i, j]), 3)}
                                               for j in best]})
        return rows, float(scores.max())
