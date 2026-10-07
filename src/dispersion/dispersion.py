"""Dispersion: how many ways a focal phrase is rendered, from the predictions of many (source, target) pairs."""
import math
import re
from collections import Counter

from src.dispersion.types import RENDERED


def normalise(text):
    """A rendering for counting: lowercased, no spaces or punctuation (but … between pieces kept)."""
    return re.sub(r'[\s\.,;:!?"\'“”‘’()（）《》，。；：！？、]', '', text.lower())


def dispersion(predictions):
    """{distinct, entropy (bits), renderings: Counter, rendered, dropped} over the RENDERED and DROPPED
    predictions of one focal phrase (NOT_FOUND say nothing about how it was rendered)."""
    rendered = [normalise(p.target_text) for p in predictions if p.status == RENDERED]
    counts = Counter(rendered)
    total = sum(counts.values())
    entropy = max(0.0, -sum(n / total * math.log2(n / total) for n in counts.values())) if total else 0.0
    return {'distinct': len(counts), 'entropy': round(entropy, 3), 'renderings': counts,
            'rendered': total, 'dropped': sum(1 for p in predictions if p.status == 'dropped')}
