"""Sentence encoders for SentenceMatcher: list of sentences -> unit vectors."""
MODEL = 'sentence-transformers/LaBSE'


def labse(model=None):
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(MODEL, device='cpu')
    return lambda texts: model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True, batch_size=32)
