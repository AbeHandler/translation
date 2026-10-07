"""Dispersion: how many ways a focal phrase is rendered, from the predictions of many (source, target) pairs."""
import math
import re
from collections import Counter

from src.dispersion.types import RENDERED


CJK = '\u4e00-\u9fff'


def normalise(text):
    """A rendering for counting: lowercased, punctuation dropped, its pieces joined (自主…武器, split by 的, counts
    as 自主武器; governance…law as governance law), spaces kept only between Latin words."""
    text = re.sub(r'[.,;:!?"\'“”‘’()（）《》，。；：！？、]', '', text.lower().replace('…', ' '))
    text = re.sub(rf'\s+(?=[{CJK}])|(?<=[{CJK}])\s+', '', text)
    return ' '.join(text.split())


def dispersion(predictions):
    """{distinct, entropy (bits), renderings: Counter, rendered, dropped} over the RENDERED and DROPPED
    predictions of one focal phrase (NOT_FOUND say nothing about how it was rendered)."""
    rendered = [normalise(p.target_text) for p in predictions if p.status == RENDERED]
    counts = Counter(rendered)
    total = sum(counts.values())
    entropy = max(0.0, -sum(n / total * math.log2(n / total) for n in counts.values())) if total else 0.0
    return {'distinct': len(counts), 'entropy': round(entropy, 3), 'renderings': counts,
            'rendered': total, 'dropped': sum(1 for p in predictions if p.status == 'dropped')}
