"""
Linking English and Chinese media storms about the same event (scripts/link_storms.py). Two kinds of evidence:
    shared seeds   both storms cite the same document (src/media_storms.py document_key: an OpenAI post, an X post)
    content        the storms' titles (and their articles' titles) are close in a multilingual embedding space
A pair is a candidate if the Chinese storm starts within a window around the English one (from -before days before
its first day to -after days after its last: Chinese coverage usually follows) and it shares a seed or its
similarity reaches min_similarity.
"""
import datetime

import numpy as np


def storm_text(storm, k=10):
    """A storm's title and the distinct titles of up to k of its articles."""
    titles = [storm.get('title', '')] + [a.get('title', '') for a in storm.get('articles', [])]
    return ' | '.join(dict.fromkeys(t.strip() for t in titles if t and t.strip()))[:2000] if k else storm['title']


def seed_keys(storm):
    return {s['document'] for s in storm.get('seeds', [])}


def lag(en, zh):
    """Days from the English storm's first day to the Chinese storm's first day."""
    return (datetime.date.fromisoformat(zh['first']) - datetime.date.fromisoformat(en['first'])).days


def in_window(en, zh, before=3, after=14):
    span = (datetime.date.fromisoformat(en['last']) - datetime.date.fromisoformat(en['first'])).days
    return -before <= lag(en, zh) <= span + after


def candidate_links(en_storms, zh_storms, en_vecs, zh_vecs, min_similarity=0.5, before=3, after=14, top=3):
    """[{en, zh, similarity, lag_days, shared_seeds}] best first, at most top English storms per Chinese storm.
    en_vecs, zh_vecs: unit vectors of the storms' texts, row-aligned."""
    sims = np.asarray(zh_vecs) @ np.asarray(en_vecs).T
    links = []
    for j, zh in enumerate(zh_storms):
        found = []
        for i, en in enumerate(en_storms):
            if not in_window(en, zh, before, after):
                continue
            shared = sorted(seed_keys(en) & seed_keys(zh))
            if shared or sims[j, i] >= min_similarity:
                found.append({'en': i, 'zh': j, 'similarity': float(sims[j, i]), 'lag_days': lag(en, zh),
                              'shared_seeds': shared})
        found.sort(key=lambda link: (-len(link['shared_seeds']), -link['similarity']))
        links += found[:top]
    return sorted(links, key=lambda link: (-len(link['shared_seeds']), -link['similarity']))
