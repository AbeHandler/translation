"""Labelling text by writing system. Counts letters by script and decides:
    zh     Han share of letters >= ZH_MIN (and no real kana or hangul)
    ja     kana share >= KANA_MIN          (Japanese mixes Han and kana)
    ko     hangul share >= HANGUL_MIN
    latin  Han share <= LATIN_MAX: a Latin-script page; langdetect names the language (usually en)
    otherwise the ambiguous middle: langdetect decides
Pages with fewer than MIN_LETTERS letters are 'unknown'."""
import re

from langdetect import DetectorFactory, LangDetectException, detect

DetectorFactory.seed = 0  # langdetect is random otherwise

HAN = re.compile(r'[㐀-䶿一-鿿豈-﫿]')
KANA = re.compile(r'[぀-ヿ]')
HANGUL = re.compile(r'[가-힯]')
LATIN = re.compile(r'[A-Za-zÀ-ɏ]')
ZH_MIN, LATIN_MAX, KANA_MIN, HANGUL_MIN, MIN_LETTERS = 0.3, 0.05, 0.05, 0.1, 50
LANGDETECT_CHARS = 5000


def script_counts(text):
    return {'han': len(HAN.findall(text)), 'kana': len(KANA.findall(text)), 'hangul': len(HANGUL.findall(text)),
            'latin': len(LATIN.findall(text))}


def langdetect_language(text):
    try:
        return detect(text[:LANGDETECT_CHARS]).split('-')[0]  # zh-cn -> zh
    except LangDetectException:
        return 'unknown'


def label_text(text):
    """(language, han share of letters, how it was decided: 'script' or 'langdetect')."""
    counts = script_counts(text)
    letters = sum(counts.values())
    if letters < MIN_LETTERS:
        return 'unknown', 0.0, 'script'
    han = counts['han'] / letters
    if counts['kana'] / letters >= KANA_MIN:
        return 'ja', han, 'script'
    if counts['hangul'] / letters >= HANGUL_MIN:
        return 'ko', han, 'script'
    if han >= ZH_MIN:
        return 'zh', han, 'script'
    return langdetect_language(text), han, 'langdetect'
