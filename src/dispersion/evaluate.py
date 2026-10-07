"""Scoring predictions against a gold set: for each gold case (focal occurrence, target, true spans or [] for
dropped), exact match and character-overlap F1 of the predicted spans."""


def chars(spans):
    return {i for a, b in spans for i in range(a, b)}


def overlap_f1(predicted, gold):
    """Character-level F1 of two span lists; both empty (dropped and predicted dropped) is 1."""
    p, g = chars(predicted), chars(gold)
    if not p and not g:
        return 1.0
    if not p or not g:
        return 0.0
    both = len(p & g)
    return 0.0 if not both else 2 * both / (len(p) + len(g))


def score(pairs):
    """pairs: [(predicted spans, gold spans)] -> {n, exact, f1}."""
    if not pairs:
        return {'n': 0, 'exact': 0.0, 'f1': 0.0}
    exact = sum(sorted(p) == sorted(g) for p, g in pairs) / len(pairs)
    f1 = sum(overlap_f1(p, g) for p, g in pairs) / len(pairs)
    return {'n': len(pairs), 'exact': round(exact, 3), 'f1': round(f1, 3)}
