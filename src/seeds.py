"""
The seed table: the documents whose transmission we follow (model.md, Seeds). A seed is a primary source
(src/primary_sources.py) linked by many AI news articles, in English news, in Chinese news or both, or one a
researcher adds by hand. One row per seed, its English and Chinese inbound links side by side. Logic only.
"""
import hashlib

from src.external_links import registered_domain
from src.seed_documents import source_kind
from src.source_texts import as_url, source_key

COLUMNS = ['seed_id', 'url', 'key', 'kind', 'organisation', 'first_seen', 'outlets', 'outlets_first', 'en_outlets',
           'en_outlets_first', 'en_first_seen', 'zh_outlets', 'zh_outlets_first', 'zh_first_seen', 'added_from',
           'text_status', 'n_chars', 'title', 'example_en', 'example_zh', 'en_storms', 'zh_storms', 'linked_storms']
MIN_TEXT_CHARS = 200   # a fetched seed with less text than this is a shell (a JavaScript-only page), not its text


def seed_id(key):
    return hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]


def organisation(key):
    """Who published it: @handle for a social post (x.com/sama/status/1 -> @sama), else the site's registered domain
    (blog.google -> blog.google, www.anthropic.com -> anthropic.com)."""
    host, _, path = key.partition('/')
    if source_kind(key) == 'social post' and path:
        return '@' + path.split('/')[0].lstrip('@')
    return registered_domain('https://' + host)


def merge_seeds(en, zh, manual=(), min_outlets=5):
    """en, zh: primary sources ({document, href, first_seen, outlets, outlets_first, example, ...}) of each corpus;
    manual: hand-picked URLs. A source is a seed if min_outlets+ outlets link it in either language; hand-picked
    ones always are. Returns the seed rows, most outlets in their first 14 days first."""
    seeds = {}

    def row(key, url):
        return seeds.setdefault(key, {
            'seed_id': seed_id(key), 'url': url, 'key': key, 'kind': source_kind(key),
            'organisation': organisation(key),
            'en_outlets': 0, 'en_outlets_first': 0, 'en_first_seen': '', 'zh_outlets': 0, 'zh_outlets_first': 0,
            'zh_first_seen': '', 'added_from': [], 'example_en': '', 'example_zh': ''})
    manual_keys = {source_key(as_url(t)) for t in manual if as_url(t)}
    for lang, sources in (('en', en), ('zh', zh)):
        for s in sources:   # hand-picked seeds keep their link counts even below min_outlets
            if s['outlets'] < min_outlets and s['document'] not in manual_keys:
                continue
            r = row(s['document'], s['href'])
            r.update({f'{lang}_outlets': s['outlets'], f'{lang}_outlets_first': s['outlets_first'],
                      f'{lang}_first_seen': s['first_seen'], f'example_{lang}': s['example']})
            r['added_from'].append(f'links_{lang}')
    for text in manual:
        url = as_url(text)
        if url:
            row(source_key(url), url)['added_from'].append('manual')
    for r in seeds.values():
        r['first_seen'] = min(filter(None, [r['en_first_seen'], r['zh_first_seen']]), default='')
        r['outlets'] = r['en_outlets'] + r['zh_outlets']
        r['outlets_first'] = r['en_outlets_first'] + r['zh_outlets_first']
        r['added_from'] = '+'.join(dict.fromkeys(r['added_from']))
    return sorted(seeds.values(), key=lambda r: (-r['outlets_first'], -r['outlets'], r['key']))


def text_status(stored):
    """'text', 'short' (fetched, under MIN_TEXT_CHARS), 'failed' (status not 200) or 'not fetched' (stored: the
    store's row for the seed, or None)."""
    if stored is None:
        return 'not fetched'
    if stored['status'] != 200:
        return 'failed'
    return 'text' if (stored['n_chars'] or 0) >= MIN_TEXT_CHARS else 'short'


def add_text_status(seeds, stored_by_key):
    """Set each seed's text_status, n_chars and title from the store ({key: stored row})."""
    for seed in seeds:
        stored = stored_by_key.get(seed['key'])
        seed.update(text_status=text_status(stored), n_chars=(stored or {}).get('n_chars') or 0,
                    title=((stored or {}).get('title') or '').replace('\t', ' ').replace('\n', ' ')[:200])
    return seeds


def add_storms(seeds, en_storm_seeds, zh_storm_seeds, storm_links):
    """Set each seed's en_storms and zh_storms (how many media storms in each language list it among the documents
    they cite: src/media_storms.py storm_seeds) and linked_storms (how many English-Chinese storm pairs share it:
    scripts/link_storms.py). en_storm_seeds, zh_storm_seeds: storm_seeds.jsonl rows; storm_links: storm_links.tsv
    rows (shared_seeds: space-separated document keys)."""
    def counts(rows):
        found = {}
        for row in rows:
            for seed in row.get('seeds', []):
                found[seed['document']] = found.get(seed['document'], 0) + 1
        return found
    en, zh, linked = counts(en_storm_seeds), counts(zh_storm_seeds), {}
    for link in storm_links:
        for key in (link.get('shared_seeds') or '').split():
            linked[key] = linked.get(key, 0) + 1
    for seed in seeds:
        seed.update(en_storms=en.get(seed['key'], 0), zh_storms=zh.get(seed['key'], 0),
                    linked_storms=linked.get(seed['key'], 0))
    return seeds
