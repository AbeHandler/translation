"""
Evidence for Fightin' Words results: where a concept comes from, to tell real differences from artefacts (one press
release syndicated to 60 sites, an outlet's footer). For a concept: the documents and outlets using it, and short
snippets of it in context from different outlets. Also dedupe: the same document published by several outlets
(syndication) counts once.
"""
import re
from collections import Counter

WIDTH = 120     # characters of context on each side of a snippet


def dedupe(docs):
    """The documents (DataFrame: lang, title, text) with each (language, first 300 characters of text) kept once,
    and each English title once: a syndicated story or press release republished by many outlets counts once.
    (Chinese titles aren't used: some sites give every page the same one.) Returns (docs, {lang: number dropped})."""
    def key(column, n=None):
        values = docs[column].fillna('').str[:n] if n else docs[column].fillna('')
        return docs['lang'] + '\t' + values.str.lower().str.replace(r'\W+', '', regex=True)
    title = key('title')
    dup = key('text', 300).duplicated() | ((docs['lang'] == 'en') & (title.str.len() > 3) & title.duplicated())
    return docs[~dup], docs.loc[dup, 'lang'].value_counts().to_dict()


def unit_regex(unit, lang):
    """A regex finding a unit in text: English words with any non-word characters between them; Chinese
    characters with optional spaces between them (known names are spaced out: ' Baidu 发布')."""
    if lang == 'en':
        return re.compile(r'(?<!\w)' + r'\W+'.join(map(re.escape, unit.split())) + r'(?!\w)', re.I)
    return re.compile(r'\s*'.join(re.escape(ch) for ch in unit if not ch.isspace()), re.I)


def snippet(text, regex, width=WIDTH):
    m = regex.search(text)
    if m is None:
        return ''
    return ('…' + text[max(0, m.start() - width):m.end() + width] + '…').replace('\n', ' ')


def evidence(docs, units, lang, k=3, top_outlets=5):
    """{documents, outlets, top_outlets, examples} for one concept in one language. docs: the language's documents
    (DataFrame: url, outlet, title, text) that use it; units: the concept's units in that language, searched for in
    the texts for snippets. Examples come from different outlets."""
    regexes = [unit_regex(u, lang) for u in units]
    examples, seen = [], set()
    for row in docs.itertuples():
        if row.outlet in seen:
            continue
        for regex in regexes:
            text = snippet(row.text, regex)
            if text:
                examples.append({'outlet': row.outlet, 'title': row.title, 'url': row.url, 'snippet': text})
                seen.add(row.outlet)
                break
        if len(examples) >= k:
            break
    return {'documents': len(docs), 'outlets': docs['outlet'].nunique(),
            'top_outlets': Counter(docs['outlet']).most_common(top_outlets), 'examples': examples}
