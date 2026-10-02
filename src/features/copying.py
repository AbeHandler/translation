"""
The copying feature: an English document contains a run of >= MIN_COPY_CHARS Chinese characters that also
appears in a Chinese document (quoted titles, terms in parentheses: 生成式人工智能服务管理暂行办法, 具有合法来源).
Found through an inverted index of 4-character shingles, not by comparing pairs. Runs found in more than max_df
Chinese documents are common terms (人工智能, 社会治理), not copies.
"""
import re
from collections import defaultdict

MIN_COPY_CHARS = 4
CHINESE_RUN = re.compile(r'[㐀-䶿一-鿿豈-﫿]{%d,}' % MIN_COPY_CHARS)


def chinese_runs(text):
    return set(CHINESE_RUN.findall(text or ''))


def shingles(text, n=MIN_COPY_CHARS):
    return {text[i:i + n] for i in range(len(text) - n + 1)}


class CopyIndex:
    """Which Chinese documents contain a given Chinese run."""

    def __init__(self, zh_texts, max_df):
        self.texts = zh_texts                      # {url: text}
        self.max_df = max_df
        self.index = defaultdict(set)
        for url, text in zh_texts.items():
            for run in chinese_runs(text):
                for shingle in shingles(run):
                    self.index[shingle].add(url)

    def documents_with(self, run):
        """Chinese documents containing run, or none if more than max_df do."""
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
