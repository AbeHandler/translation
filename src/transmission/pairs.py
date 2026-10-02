"""
The data layer of model1 (docs/model1.md): the (English document i, Chinese document j) pair table.
    doc_en, doc_zh   the documents' URLs
    L                1 if i links to j
    c                1 if i contains a run of >= MIN_COPY_CHARS Chinese characters that also appears in j
    y                hand label for "i transmits j" (1/0), '' if unlabelled
Candidates are the linked pairs plus, for each English document, its nearest Chinese documents by embedding, so
the table isn't dominated by easy negatives. Logic only: texts, links and vectors come in as arguments.
"""
import csv
import re

import numpy as np

MIN_COPY_CHARS = 4
CHINESE_RUN = re.compile(r'[㐀-䶿一-鿿豈-﫿]{%d,}' % MIN_COPY_CHARS)
COLUMNS = ['doc_en', 'doc_zh', 'L', 'c', 'y']


def chinese_runs(text):
    """Runs of >= MIN_COPY_CHARS Chinese characters in a text (an English article's quoted titles, terms in
    parentheses: 生成式人工智能服务管理暂行办法, 具有合法来源)."""
    return set(CHINESE_RUN.findall(text or ''))


def copies(en_text, zh_text):
    """1 if any Chinese run of the English text occurs in the Chinese text, else 0."""
    return int(any(run in (zh_text or '') for run in chinese_runs(en_text)))


def nearest(en_vectors, zh_vectors, k):
    """For each English row, the indices of its k most similar Chinese rows (unit vectors: dot = cosine)."""
    if len(zh_vectors) == 0 or k == 0:
        return [[] for _ in range(len(en_vectors))]
    sims = np.asarray(en_vectors) @ np.asarray(zh_vectors).T
    k = min(k, sims.shape[1])
    return [list(row) for row in np.argsort(-sims, axis=1)[:, :k]]


def build_pairs(links, neighbours, en_texts, zh_texts, labels=None):
    """Rows {doc_en, doc_zh, L, c, y} for every linked pair and every (English doc, neighbour) pair whose two
    texts are known. links: (doc_en, doc_zh) pairs; neighbours: {doc_en: [doc_zh, ...]}; en_texts, zh_texts:
    {url: text}; labels: {(doc_en, doc_zh): 0/1}."""
    labels = labels or {}
    linked = {(en, zh) for en, zh in links}
    candidates = linked | {(en, zh) for en, zhs in neighbours.items() for zh in zhs}
    return [{'doc_en': en, 'doc_zh': zh, 'L': int((en, zh) in linked), 'c': copies(en_texts[en], zh_texts[zh]),
             'y': labels.get((en, zh), '')}
            for en, zh in sorted(candidates) if en in en_texts and zh in zh_texts]


def write_pairs(rows, path):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS + [k for k in rows[0] if k not in COLUMNS] if rows else COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def read_pairs(path):
    """(rows, L, c, y) with y NaN where unlabelled."""
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    y = np.array([float(r['y']) if str(r['y']).strip() != '' else np.nan for r in rows])
    return rows, np.array([float(r['L']) for r in rows]), np.array([float(r['c']) for r in rows]), y


def read_labels(path):
    """{(doc_en, doc_zh): 0/1} from a CSV with columns doc_en, doc_zh, y."""
    with open(path, newline='', encoding='utf-8') as f:
        return {(r['doc_en'], r['doc_zh']): int(r['y']) for r in csv.DictReader(f) if str(r['y']).strip() != ''}
