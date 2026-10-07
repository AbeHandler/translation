"""
Target transmission (model.md, step 3): which seeds cross into Chinese news, and into which articles. Every
(seed, Chinese article) pair with any evidence becomes a row; the evidence:
    link         the Chinese article links the seed (step 1's Chinese link tables, via step 2's citations)
    screenshot   it shows an image of the seed's text (src/source_matching.py on its English screenshots)
    en_quote     it keeps a passage of the seed verbatim, in English (step 2's quotes)
    doc_sim      cosine of the seed's and the article's LaBSE embeddings (a multilingual model), binned
    sent_sim     the best LaBSE cosine of any seed sentence with any article sentence, binned; >= 0.8 is a
                 translation
    date_gap     days from the seed's first appearance to the article, binned
Pairs that only cite the seed ("says it happened, links the doc") have link evidence but low sent_sim, which tells
them apart from translations. model1 (src/model/model1.py) combines the evidence into P(crossed). Logic only.
"""
import numpy as np

from src.salience import days_between

MODEL = 'sentence-transformers/LaBSE'
WINDOW = (-3, 60)            # candidate Chinese articles: from 3 days before to 60 days after the seed appears
TOP_K = 50                   # candidates per seed scored sentence by sentence
LEAD_CHARS = 3000            # text kept per Chinese article (embedding and sentence scoring)
TRANSLATION_SIM = 0.8        # a sentence pair this similar is a translation (src/restatement/align.py)

DOC_SIM_EDGES = [0.3, 0.4, 0.5, 0.6]
SENT_SIM_EDGES = [0.5, 0.6, 0.7, 0.8]
DATE_EDGES = [-3, 4, 15, 61]          # before the seed (< -3), 0-3 days, 4-14, 15-60, later
FEATURES = ['link', 'screenshot', 'en_quote', 'doc_sim', 'sent_sim', 'date_gap']
N_LEVELS = [2, 2, 2, len(DOC_SIM_EDGES) + 1, len(SENT_SIM_EDGES) + 1, len(DATE_EDGES) + 1]
POSITIVE_HINT = {0: [1], 1: [1], 2: [1], 3: [len(DOC_SIM_EDGES)], 4: [len(SENT_SIM_EDGES)], 5: [1, 2]}


def binned(value, edges):
    """Level code of a value (None/NaN -> -1)."""
    if value is None or value != value:
        return -1
    return int(np.digitize([value], edges)[0])


def feature_row(pair):
    """Codes for one pair ({link, screenshot, en_quote, doc_sim, sent_sim, date_gap}; scores may be None)."""
    return [int(bool(pair['link'])), int(bool(pair['screenshot'])), int(bool(pair['en_quote'])),
            binned(pair['doc_sim'], DOC_SIM_EDGES), binned(pair['sent_sim'], SENT_SIM_EDGES),
            binned(pair['date_gap'], DATE_EDGES)]


def sentence_scores(seed_vectors, article_vectors):
    """(best cosine, number of seed sentences with a translation-like match) between two sets of unit vectors."""
    if not len(seed_vectors) or not len(article_vectors):
        return None, 0
    sims = np.asarray(seed_vectors) @ np.asarray(article_vectors).T
    return float(sims.max()), int((sims.max(axis=1) >= TRANSLATION_SIM).sum())


def seed_summary(seed, pairs, threshold=0.5):
    """Per seed: whether it crossed (any pair with P(crossed) >= threshold), how many Chinese articles and outlets,
    the first such article's date and its lag, and the evidence those pairs carry."""
    crossed = [p for p in pairs if p['p_crossed'] >= threshold]
    first = min((p['date'] for p in crossed if p['date']), default='')
    return {'seed_id': seed['seed_id'], 'url': seed['url'], 'kind': seed['kind'], 'organisation': seed['organisation'],
            'first_seen': seed['first_seen'], 'crossed': int(bool(crossed)), 'zh_articles': len(crossed),
            'zh_outlets': len({p['outlet'] for p in crossed}), 'first_zh': first,
            'lag_days': days_between(seed['first_seen'], first) if seed['first_seen'] and first else '',
            'by_link': sum(p['link'] for p in crossed), 'by_screenshot': sum(p['screenshot'] for p in crossed),
            'by_en_quote': sum(p['en_quote'] for p in crossed),
            'translated': sum(1 for p in crossed if (p['sent_sim'] or 0) >= TRANSLATION_SIM),
            'candidates': len(pairs), 'max_p': round(max((p['p_crossed'] for p in pairs), default=0.0), 3)}
