"""
Selections for Fightin' Words: which documents an experiment samples (all AI documents, or those naming OpenAI,
Anthropic ...), from a table of named selections (config/fightin_selections.tsv): a regex on title and text
(case-insensitive) and a date span. The regex is first tried on a page's raw HTML, so pages that can't match are
skipped before their text is extracted.
"""
import re
from dataclasses import dataclass

import pandas as pd


@dataclass
class Selection:
    name: str
    pattern: str = ''
    start: str = ''      # YYYY-MM-DD, inclusive
    end: str = ''

    def __post_init__(self):
        self.regex = re.compile(self.pattern, re.I) if self.pattern else None
        self.raw_regex = re.compile(self.pattern.encode('utf-8'), re.I) if self.pattern else None

    def may_match(self, html):
        """False if the page's raw HTML (bytes or str) can't contain the pattern (a cheap pre-filter)."""
        if self.raw_regex is None:
            return True
        if isinstance(html, str):
            return bool(self.regex.search(html))
        return bool(self.raw_regex.search(html))

    def matches(self, title, text, date):
        """The pattern in title or text, and the date (YYYY-MM-DD) within the span; an undated document fails a
        span."""
        if self.regex and not (self.regex.search(title or '') or self.regex.search(text or '')):
            return False
        date = (date or '')[:10]
        if (self.start or self.end) and not date:
            return False
        return not ((self.start and date < self.start) or (self.end and date > self.end))


def read_selections(path):
    """{name: Selection} of a selections file (tab-separated: name, pattern, from, to; # comments)."""
    table = pd.read_csv(path, sep='\t', comment='#', dtype=str, keep_default_na=False)
    if table['name'].duplicated().any():
        raise SystemExit(f'{path}: duplicate selection names')
    return {row['name']: Selection(row['name'], row.get('pattern', ''), row.get('from', ''), row.get('to', ''))
            for row in table.to_dict('records')}
