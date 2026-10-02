"""
The data layer of model1 (docs/model1.md): the (English document i, Chinese document j) pairs, without ever
building the full English x Chinese table.

Under model1 a pair only matters through its cell (L, c, y): every unlabelled pair with no link and no copy
(L = 0, c = 0) has the same likelihood term and the same posterior. So the table is sparse plus one count:
    one row per pair that is linked (L = 1), copies (c = 1) or is labelled (y given)
    one background row (doc_en = doc_zh = '*', L = 0, c = 0, unlabelled) whose weight w is the number of other
        pairs in the universe
Every row has a weight w (1 for real pairs), and the model sums log-likelihood terms times w.

The universe is all (English doc, Chinese doc) pairs published within `window_days` of each other (the English
doc no earlier than window_days before the Chinese one): it is counted from the two documents' dates, not
enumerated.

Copies are found without comparing every pair: an inverted index maps each 4-character Chinese shingle to the
Chinese documents containing it; a run in an English text is looked up through its shingles and confirmed by
substring search. Runs that occur in more than `max_df` Chinese documents (common words: 人工智能, 社会治理)
don't count as copies: they would make chance copying far likelier than gamma_0 = eps assumes.
"""
import bisect
import csv
import re
from collections import defaultdict

import numpy as np

MIN_COPY_CHARS = 4
CHINESE_RUN = re.compile(r'[㐀-䶿一-鿿豈-﫿]{%d,}' % MIN_COPY_CHARS)
COLUMNS = ['doc_en', 'doc_zh', 'L', 'c', 'y', 'w']
BACKGROUND = '*'


def chinese_runs(text):
    """Runs of >= MIN_COPY_CHARS Chinese characters in a text (an English article's quoted titles, terms in
    parentheses: 生成式人工智能服务管理暂行办法, 具有合法来源)."""
    return set(CHINESE_RUN.findall(text or ''))


def shingles(text, n=MIN_COPY_CHARS):
    return {text[i:i + n] for i in range(len(text) - n + 1)}


class CopyIndex:
    """Which Chinese documents contain a given Chinese run, from an inverted index of 4-character shingles."""

    def __init__(self, zh_texts, max_df):
        self.texts = zh_texts                      # {url: text}
        self.max_df = max_df
        self.index = defaultdict(set)
        for url, text in zh_texts.items():
            for run in chinese_runs(text):
                for shingle in shingles(run):
                    self.index[shingle].add(url)

    def documents_with(self, run):
        """Chinese documents containing run, or none if more than max_df do (a common term, not a copy)."""
        candidates = None
        for shingle in shingles(run):
            docs = self.index.get(shingle, set())
            candidates = docs if candidates is None else candidates & docs
            if not candidates:
                return set()
        found = {url for url in candidates if run in self.texts[url]}
        return found if len(found) <= self.max_df else set()

    def copied(self, en_text):
        """{Chinese doc url: the runs of en_text it contains}."""
        out = defaultdict(set)
        for run in chinese_runs(en_text):
            for url in self.documents_with(run):
                out[url].add(run)
        return out


def universe_size(en_dates, zh_dates, window_days):
    """Number of (English, Chinese) date pairs with 0 <= en - zh <= window_days (dates as day numbers)."""
    zh_sorted = sorted(zh_dates)
    return sum(bisect.bisect_right(zh_sorted, d) - bisect.bisect_left(zh_sorted, d - window_days) for d in en_dates)


def build_pairs(links, en_texts, copy_index, labels, n_universe):
    """Sparse rows {doc_en, doc_zh, L, c, y, w, runs} for linked, copying or labelled pairs, plus the
    background row of weight n_universe minus those. links: (doc_en, doc_zh); en_texts: {url: text};
    labels: {(doc_en, doc_zh): 0/1}."""
    rows = {}
    for en, zh in links:
        rows[(en, zh)] = {'doc_en': en, 'doc_zh': zh, 'L': 1, 'c': 0, 'y': '', 'w': 1, 'runs': ''}
    for en, text in en_texts.items():
        for zh, runs in copy_index.copied(text).items():
            row = rows.setdefault((en, zh), {'doc_en': en, 'doc_zh': zh, 'L': 0, 'c': 0, 'y': '', 'w': 1, 'runs': ''})
            row['c'], row['runs'] = 1, '|'.join(sorted(runs))
    for (en, zh), y in labels.items():
        rows.setdefault((en, zh), {'doc_en': en, 'doc_zh': zh, 'L': 0, 'c': 0, 'y': '', 'w': 1, 'runs': ''})['y'] = y
    out = [rows[key] for key in sorted(rows)]
    out.append({'doc_en': BACKGROUND, 'doc_zh': BACKGROUND, 'L': 0, 'c': 0, 'y': '',
                'w': max(n_universe - len(out), 0), 'runs': ''})
    return out


def write_pairs(rows, path):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        extra = [k for k in rows[0] if k not in COLUMNS] if rows else []
        writer = csv.DictWriter(f, fieldnames=COLUMNS + extra)
        writer.writeheader()
        writer.writerows(rows)


def read_pairs(path):
    """(rows, L, c, y, w) with y NaN where unlabelled; w is 1 for files written before weights existed."""
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    def column(key, default=None):
        return np.array([float(r.get(key) or default) for r in rows])
    y = np.array([float(r['y']) if str(r['y']).strip() != '' else np.nan for r in rows])
    return rows, column('L'), column('c'), y, column('w', 1)


def read_labels(path):
    """{(doc_en, doc_zh): 0/1} from a CSV with columns doc_en, doc_zh, y."""
    with open(path, newline='', encoding='utf-8') as f:
        return {(r['doc_en'], r['doc_zh']): int(r['y']) for r in csv.DictReader(f) if str(r['y']).strip() != ''}
