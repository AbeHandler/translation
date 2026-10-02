"""
The feature matrix of candidate pairs (src/features/candidates.py) for the transmission model: one row per
(English doc, Chinese doc) pair, small integer codes per feature, -1 = missing.
    link        1 if the English doc links to the Chinese doc
    quote_link  1 if that link is in quotation marks (src/features/quoting.py), 0 if not, -1 if no link or the
                English page's HTML isn't at hand
    copy        1 if it copies a Chinese run from it (src/features/copying.py)
    similarity  cosine of the two documents' embeddings, binned (SIM_EDGES)
    date_gap    days from the Chinese doc's publication to the English doc's, binned (DATE_EDGES)
(Screenshots are in the spec, not built yet.) Logic only: links, copies, vectors and dates come in as arguments.
"""
import csv

import numpy as np

SIM_EDGES = [0.3, 0.4, 0.5, 0.6]             # similarity levels: < 0.3, 0.3-0.4, 0.4-0.5, 0.5-0.6, >= 0.6
DATE_EDGES = [0, 4, 31, 366]                 # gap levels: English first (< 0), 0-3, 4-30, 31-365, > 365 days
FEATURES = ['link', 'quote_link', 'copy', 'similarity', 'date_gap']
N_LEVELS = [2, 2, 2, len(SIM_EDGES) + 1, len(DATE_EDGES) + 1]
POSITIVE_HINT = {0: [1], 1: [1], 2: [1], 3: [len(SIM_EDGES)], 4: [1]}   # levels that suggest transmission


def binned(values, edges):
    """Level codes for values (NaN -> -1)."""
    values = np.asarray(values, dtype=float)
    return np.where(np.isnan(values), -1, np.digitize(values, edges)).astype(int)


def feature_matrix(pairs, links, quoted, copies, en_vectors, zh_vectors, en_days, zh_days):
    """X: (len(pairs), len(FEATURES)) codes. links: set of (en, zh); quoted: {(en, zh): 1/0/-1}; copies: {en:
    {zh: runs}}; *_vectors: {url: unit vector} (missing -> similarity -1); *_days: {url: day number} (missing ->
    date_gap -1)."""
    rows = []
    for en, zh in pairs:
        sim = float(en_vectors[en] @ zh_vectors[zh]) if en in en_vectors and zh in zh_vectors else np.nan
        gap = en_days[en] - zh_days[zh] if en_days.get(en) is not None and zh_days.get(zh) is not None else np.nan
        quote = quoted.get((en, zh), -1) if (en, zh) in links else -1
        rows.append([int((en, zh) in links), quote, int(zh in copies.get(en, {})), sim, gap])
    raw = np.array(rows, dtype=float).reshape(len(pairs), 5)
    return np.column_stack([raw[:, 0], raw[:, 1], raw[:, 2], binned(raw[:, 3], SIM_EDGES),
                            binned(raw[:, 4], DATE_EDGES)]).astype(int)


def aggregate(X, y):
    """Identical rows collapsed: (unique X, their y (labelled rows stay apart), weights, row -> unique index)."""
    keys = np.column_stack([X, np.where(np.isnan(y), -9, y)])
    unique, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    y_unique = unique[:, -1].astype(float)
    y_unique[y_unique == -9] = np.nan
    return unique[:, :-1].astype(int), y_unique, counts.astype(float), inverse.reshape(-1)


def write_pairs(path, pairs, X, extra=None):
    """CSV doc_en, doc_zh, one column per feature, plus extra columns ({name: values})."""
    extra = extra or {}
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['doc_en', 'doc_zh'] + FEATURES + list(extra))
        for i, (en, zh) in enumerate(pairs):
            writer.writerow([en, zh] + [int(v) for v in X[i]] + [values[i] for values in extra.values()])


def read_pairs(path):
    """(pairs, X, other columns as {name: list})."""
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    pairs = [(r['doc_en'], r['doc_zh']) for r in rows]
    X = np.array([[int(r[name]) for name in FEATURES] for r in rows], dtype=int).reshape(len(rows), len(FEATURES))
    others = [k for k in (rows[0] if rows else {}) if k not in FEATURES + ['doc_en', 'doc_zh']]
    return pairs, X, {k: [r[k] for r in rows] for k in others}


def read_labels(path):
    """{(doc_en, doc_zh): 0/1} from a CSV with columns doc_en, doc_zh, y."""
    with open(path, newline='', encoding='utf-8') as f:
        return {(r['doc_en'], r['doc_zh']): int(r['y']) for r in csv.DictReader(f) if str(r['y']).strip() != ''}
