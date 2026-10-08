"""
Known renderings: Chinese names (companies, products, people) written in English in a Chinese text before it is
counted, so a name matches its English across languages even where the multilingual embedding can't link them
(文心一言 -> ERNIE Bot). The table: config/fightin_known_renderings.tsv.
"""
import re

import pandas as pd


class KnownRenderings:
    def __init__(self, pairs):
        """pairs: [(chinese, english)]; longer Chinese names are replaced first (文心一言 before 文心)."""
        self.english = dict(pairs)
        names = sorted(self.english, key=len, reverse=True)
        self.regex = re.compile('|'.join(map(re.escape, names))) if names else None

    @classmethod
    def read(cls, path):
        table = pd.read_csv(path, sep='\t', comment='#', dtype=str, keep_default_na=False)
        return cls(zip(table['chinese'], table['english']))

    def apply(self, text):
        """The text with each known Chinese name replaced by its English, set off by spaces."""
        if self.regex is None:
            return text
        return self.regex.sub(lambda m: f' {self.english[m.group()]} ', text)
