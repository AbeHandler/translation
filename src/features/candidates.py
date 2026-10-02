"""
Mining candidate pairs: an (English doc, Chinese doc) pair goes into the feature matrix if any feature fires for
it (a link, a copy, a screenshot, similar embeddings, close dates). For now the candidates are the linked pairs
only; the other sources are added here as they're built, each without comparing all pairs (the copy index,
nearest-neighbour search on embeddings, date blocking).
"""


def mine_candidates(links, copies=None):
    """Sorted (en, zh) pairs: every linked pair, plus every copying pair if copies ({en: {zh: runs}}) is given."""
    found = set(links)
    for en, by_zh in (copies or {}).items():
        found.update((en, zh) for zh in by_zh)
    return sorted(found)
