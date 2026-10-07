"""
Source transmission (model.md): how much attention each seed gets in each ecosystem, and what its coverage takes
from it. For one citing article: the verbatim passages it shares with the seed's text (five-word phrases, as in
src/source_matching.py). For one seed: counts of citing articles and outlets per language, how soon they came,
and how many quote it. Logic only.
"""
import datetime

from src.source_matching import overlap_spans, phrases

MIN_PASSAGE_WORDS = 5   # a quoted passage is at least one shared five-word phrase
SPREAD_DAYS = 14

CITATION_COLUMNS = [('seed_id', 'string'), ('key', 'string'), ('language', 'string'), ('article', 'string'),
                    ('outlet', 'string'), ('date', 'string'), ('title', 'string'), ('text', 'string'),
                    ('n_chars', 'int32'), ('n_passages', 'int32'), ('n_quoted_words', 'int32')]
QUOTE_COLUMNS = [('seed_id', 'string'), ('key', 'string'), ('language', 'string'), ('article', 'string'),
                 ('outlet', 'string'), ('date', 'string'), ('passage', 'string'), ('n_words', 'int32')]
SALIENCE_COLUMNS = ['seed_id', 'url', 'kind', 'organisation', 'first_seen', 'text_status'] + [
    f'{lang}_{name}' for lang in ('en', 'zh') for name in
    ('articles', 'outlets', 'outlets_14d', 'first_citation', 'lag_days', 'with_text', 'quoting', 'quoting_share')]


def quoted_passages(article_text, seed_phrases):
    """The passages of the article that are verbatim in the seed (lowercased words; see overlap_spans)."""
    shared = phrases(article_text) & seed_phrases
    return [p for p in overlap_spans(article_text, shared) if len(p.split()) >= MIN_PASSAGE_WORDS] if shared else []


def days_between(a, b):
    return (datetime.date.fromisoformat(b[:10]) - datetime.date.fromisoformat(a[:10])).days


def seed_salience(seed, citations):
    """One salience row for a seed (a seeds.tsv row) from its citations ({language, article, outlet, date,
    n_chars, n_passages}); per language: citing articles and outlets, outlets within SPREAD_DAYS of the seed's
    first_seen, the first citation and its lag in days, articles with text, and those quoting it verbatim."""
    row = {k: seed.get(k, '') for k in ('seed_id', 'url', 'kind', 'organisation', 'first_seen', 'text_status')}
    for lang in ('en', 'zh'):
        cites = [c for c in citations if c['language'] == lang]
        dated = [c for c in cites if c['date']]
        first = min((c['date'] for c in dated), default='')
        early = {c['outlet'] for c in dated if seed['first_seen'] and 0 <= days_between(seed['first_seen'], c['date'])
                 <= SPREAD_DAYS}
        with_text = [c for c in cites if c['n_chars']]
        quoting = [c for c in with_text if c['n_passages']]
        row.update({f'{lang}_articles': len({c['article'] for c in cites}),
                    f'{lang}_outlets': len({c['outlet'] for c in cites}), f'{lang}_outlets_14d': len(early),
                    f'{lang}_first_citation': first,
                    f'{lang}_lag_days': days_between(seed['first_seen'], first) if first and seed['first_seen'] else '',
                    f'{lang}_with_text': len(with_text), f'{lang}_quoting': len(quoting),
                    f'{lang}_quoting_share': round(len(quoting) / len(with_text), 3) if with_text else ''})
    return row
