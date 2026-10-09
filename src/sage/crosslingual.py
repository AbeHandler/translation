"""
English and Chinese documents on one vocabulary of concepts, for a joint SAGE: each Chinese unit is mapped to its
nearest English unit when the multilingual embedding puts them close (cosine >= threshold: 资本开支 -> capital
expenditure); Latin-script units (names: nvidia, jensen huang) are their own concept in both languages; other
Chinese units stay their own (Chinese-only) concept. The same mapping as Fightin' Words (src/fightin/concepts.py).
"""
from src.fightin.concepts import for_embedding, pivot_concepts
from src.fightin.embeddings.backends import from_encoder
from src.fightin.embeddings.index import VectorIndex


def concept_map(en_vocab, zh_vocab, encode, threshold=0.7, say=None):
    """{Chinese unit: (concept, cosine)}. encode: a list of texts -> vectors (e.g. LaBSE); English abbreviations
    are spelled out for the embedding only (AI -> artificial intelligence)."""
    index = VectorIndex()
    for lang, vocab in (('en', en_vocab), ('zh', zh_vocab)):
        index.add(*from_encoder(vocab, lambda units: encode([for_embedding(u) for u in units]), say=say), lang=lang)
    return pivot_concepts(index, zh_vocab, threshold)


def to_concepts(found, langs, mapping, stop=frozenset()):
    """Each document's units as concepts: Chinese ones mapped, English ones as they are; stopword concepts (a
    Chinese function word mapped to "the") left out."""
    out = []
    for units, lang in zip(found, langs):
        concepts = (mapping.get(u, (u, 0))[0] for u in units) if lang == 'zh' else units
        out.append([c for c in concepts if c not in stop])
    return out
