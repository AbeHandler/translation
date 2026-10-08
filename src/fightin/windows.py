"""
Context windows: instead of a whole document, only the words around each mention of the selection's pattern
(Anthropic +/- 200 words), so the comparison is about how the subject is talked about, not everything else the
documents cover. Words are the tokenizer's (English words, Chinese jieba words), not punctuation or numbers.
Overlapping windows merge; separate ones are joined with a break, so no phrase spans two of them.
"""
from src.dispersion.tokens import tokens
from src.fightin.concepts import normalise

BREAK = '\n。\n'      # punctuation: phrases (src/fightin/units.py) never cross it


def windows(text, regex, lang, size):
    """The parts of text within size words of a match of regex, joined by BREAK ('' if nothing matches)."""
    spans = [(m.start(), m.end()) for m in regex.finditer(text)]
    if not spans:
        return ''
    toks = [t for t in tokens(text, lang) if normalise(t[0])]    # words only: no punctuation or numbers
    hits = [k for k, (_, a, b) in enumerate(toks) if any(a < e and s < b for s, e in spans)]
    ranges = []
    for k in hits:
        lo, hi = max(0, k - size), min(len(toks) - 1, k + size)
        if ranges and lo <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], hi))
        else:
            ranges.append((lo, hi))
    return BREAK.join(text[toks[lo][1]:toks[hi][2]] for lo, hi in ranges)
