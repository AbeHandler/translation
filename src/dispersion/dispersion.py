"""Dispersion: how many ways a focal phrase is rendered, from the predictions of many (source, target) pairs."""
import math
import re
from collections import Counter

from src.dispersion.types import DROPPED, RENDERINGS


CJK = '\u4e00-\u9fff'


def normalise(text):
    """A rendering for counting: lowercased, punctuation dropped, its pieces joined (自主…武器, split by 的, counts
    as 自主武器; governance…law as governance law), spaces kept only between Latin words."""
    text = re.sub(r'[.,;:!?"\'“”‘’()（）《》，。；：！？、]', '', text.lower().replace('…', ' '))
    text = re.sub(rf'\s+(?=[{CJK}])|(?<=[{CJK}])\s+', '', text)
    return ' '.join(text.split())


def dispersion(predictions):
    """{distinct, entropy (bits), renderings: Counter, rendered, dropped} of one focal phrase's predictions: the
    renderings of those that crossed (verbatim, translated, paraphrased)."""
    rendered = [normalise(p.target_text) for p in predictions if p.uptake in RENDERINGS]
    counts = Counter(rendered)
    total = sum(counts.values())
    entropy = max(0.0, -sum(n / total * math.log2(n / total) for n in counts.values())) if total else 0.0
    return {'distinct': len(counts), 'entropy': round(entropy, 3), 'renderings': counts,
            'rendered': total, 'dropped': sum(1 for p in predictions if p.uptake == DROPPED)}


def selection(predictions):
    """{uptake: share} of one focal phrase's occurrences: how often it crossed verbatim, translated, paraphrased, or
    was dropped."""
    counts = Counter(p.uptake for p in predictions)
    return {u: round(counts[u] / len(predictions), 3) for u in (*RENDERINGS, DROPPED)} if predictions else {}
