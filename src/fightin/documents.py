"""
Checks on sampled documents' text, for keeping the English side English and news:
    is_english     CC-NEWS's language tag is wrong for some pages (Romanian ones gave the phrase "apare prima"):
                   the text must be mostly ASCII letters and use English function words
    is_templated   machine-written stock notices (MarketBeat's network of sites: "shares per day", "closing price",
                   "buy rating"), the same template thousands of times
"""
import re

FUNCTION_WORDS = frozenset('the of and to a in is for that on with as by from at are was be this it an or we you '
                           'they he she has have not but will can its their our your'.split())
MIN_FUNCTION_SHARE = 0.2     # English prose: about 40-50% of words are function words; other languages: near 0
MAX_NON_ASCII = 0.01         # letters with diacritics (Romanian ă â î ș ț, French, German...) per letter
TEMPLATED = re.compile(r'MarketBeat|marketbeat\.com|shares of the company traded hands|'
                       r'(?:sell|hold|buy) rating (?:on|to) the stock', re.I)
WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def is_english(text):
    words = WORD.findall(text.lower())
    if len(words) < 50:
        return False
    letters = sum(len(w) for w in words)
    non_ascii = sum(1 for w in words for ch in w if not ch.isascii())
    function = sum(w in FUNCTION_WORDS for w in words)
    return non_ascii / letters <= MAX_NON_ASCII and function / len(words) >= MIN_FUNCTION_SHARE


def is_templated(text):
    return bool(TEMPLATED.search(text))
