"""
Conditioning for Fightin' Words: which documents of the sample to compare, as a list of document ids. A selection
is a plain text file, one id per line, so it can come from anywhere (a hand-made list, another script); select_ids
makes one from the sample by a regex on title and text (e.g. 'OpenAI', 'Anthropic|Claude') and a date span.
"""
import hashlib
import re


def doc_id(url):
    """A document's id: the first 16 hex digits of its URL's sha1."""
    return hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]


def select_ids(docs, pattern=None, start=None, end=None):
    """The ids of the documents (a DataFrame with url, title, text, date) whose title or text matches the regex
    (case-insensitive) and whose date (YYYY-MM-DD) is within [start, end]; a document without a date is left out
    when a span is given."""
    keep = docs.index == docs.index
    if pattern:
        regex = re.compile(pattern, re.I)
        keep &= (docs['title'].fillna('') + '\n' + docs['text'].fillna('')).map(lambda t: bool(regex.search(t)))
    dates = docs['date'].fillna('').str[:10]
    if start:
        keep &= (dates != '') & (dates >= start)
    if end:
        keep &= (dates != '') & (dates <= end)
    return [doc_id(u) for u in docs.loc[keep, 'url']]


def read_ids(path):
    with open(path, encoding='utf-8') as f:
        return {line.strip() for line in f if line.strip() and not line.startswith('#')}


def write_ids(ids, path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(''.join(f'{i}\n' for i in ids))
