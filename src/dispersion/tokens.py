"""Words with their character offsets, for word aligners: English by regex, Chinese by jieba (which keeps Latin runs
like "AI" or "GPT-4o" whole)."""
import re

WORD = re.compile(r"[A-Za-z0-9]+(?:[-'.][A-Za-z0-9]+)*|[^\sA-Za-z0-9]")


def tokens(text, lang):
    """[(word, start, end)] of the text, spaces left out."""
    if lang == 'zh':
        import jieba
        return [(w, a, b) for w, a, b in jieba.tokenize(text) if w.strip()]
    return [(m.group(), m.start(), m.end()) for m in WORD.finditer(text)]


def merge_spans(spans, text):
    """Adjacent spans (only spaces between them) joined: aligned words -> the pieces of a rendering."""
    out = []
    for a, b in sorted(spans):
        if out and not text[out[-1][1]:a].strip():
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out
