"""
Checks on sampled documents' text, for keeping the English side news:
    is_templated   machine-written stock notices (MarketBeat's network of sites: "shares per day", "closing price",
                   "buy rating"), the same template thousands of times
"""
import re

TEMPLATED = re.compile(r'MarketBeat|marketbeat\.com|shares of the company traded hands|'
                       r'(?:sell|hold|buy) rating (?:on|to) the stock', re.I)


def is_templated(text):
    return bool(TEMPLATED.search(text))
