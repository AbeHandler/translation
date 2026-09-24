"""
Source documents for MT, listed in a YAML config (config/mt_sources.yaml), each parsed its own way:

    - id: amodei_pace_frontier           # names the files and the segments (<id>_<n>)
      src_lang: en
      tgt_lang: zh
      url: https://darioamodei.com/...   # fetched, or
      text: "..."                        # given inline (e.g. a tweet read off a screenshot)
      selector: article .w-richtext      # optional: the element holding the text; default: newspaper4k
      unit: sentence                     # sentence (default) or document (the whole text, one segment)
      source_url: https://...            # optional, when the text was found somewhere other than url
      metadata: {author: ...}            # optional, kept with every segment

fetch_html() and extract_text() get a fetched source's text; segments() splits it into Segments, each with
its neighbouring sentences as context, ready for the MT queue.
"""
import json
import re
from dataclasses import dataclass, field

import httpx
import yaml
from newspaper import Article
from parsel import Selector

from src.translation.segments import Segment

UNITS = ('sentence', 'document')
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/124.0 Safari/537.36')
BLOCKS = ('./descendant::*[self::p or self::h1 or self::h2 or self::h3 or self::h4 or self::li or self::blockquote]'
          '[not(ancestor::p or ancestor::li or ancestor::blockquote)]')
HEADINGS = ('h1', 'h2', 'h3', 'h4')
# Sentence ends: . ! ? (maybe then a closing quote or bracket), whitespace, and a capital, quote or digit;
# or 。！？ (maybe then a closing quote). Lookbehinds must be fixed-width, hence the alternatives.
SENTENCE_END = re.compile(r'(?:(?<=[.!?])|(?<=[.!?][\"\'”’)\]]))\s+(?=[A-Z0-9\"“‘(\[])'
                          r'|(?<=[。！？])(?![”’」』）])|(?<=[。！？][”’」』）])')
ABBREVIATIONS = ('e.g.', 'i.e.', 'etc.', 'vs.', 'Mr.', 'Mrs.', 'Ms.', 'Dr.', 'St.', 'U.S.', 'U.K.', 'No.')


@dataclass(frozen=True)
class Source:
    id: str
    src_lang: str
    tgt_lang: str
    url: str = ''
    text: str = ''
    selector: str = ''
    unit: str = 'sentence'
    source_url: str = ''
    metadata: dict = field(default_factory=dict, hash=False)


def read_sources(path):
    with open(path, encoding='utf-8') as f:
        entries = yaml.safe_load(f) or []
    sources = [Source(**entry) for entry in entries]
    ids = [s.id for s in sources]
    if len(set(ids)) != len(ids):
        raise ValueError(f'{path} has duplicate source ids')
    for s in sources:
        if bool(s.url) == bool(s.text):
            raise ValueError(f'source {s.id}: give exactly one of url or text')
        if s.unit not in UNITS:
            raise ValueError(f'source {s.id}: unit must be one of {UNITS}')
    return sources


def fetch_html(url):
    response = httpx.get(url, headers={'User-Agent': USER_AGENT}, follow_redirects=True, timeout=60)
    response.raise_for_status()
    return response.text


def extract_text(html, url, selector=''):
    """The document's text: paragraphs separated by blank lines, headings as '## ...' lines (not translated).
    With a selector, from that element's paragraphs, headings and list items, stopping at a 'Footnotes'
    heading; otherwise newspaper4k's article text."""
    if not selector:
        article = Article(url, fetch_images=False)
        article.download(input_html=html)
        article.parse()
        return article.text
    containers = Selector(html).css(selector)
    if not containers:
        raise ValueError(f'selector {selector!r} matches nothing at {url}')
    blocks = []
    for block in containers[0].xpath(BLOCKS):
        text = ' '.join(block.xpath('string(.)').get().split())
        if block.root.tag in HEADINGS:
            if text == 'Footnotes':
                break
            blocks.append(f'## {text}')
        elif text:
            blocks.append(text)
    return '\n\n'.join(blocks)


def split_sentences(paragraph):
    protected = paragraph
    for i, abbreviation in enumerate(ABBREVIATIONS):
        protected = protected.replace(abbreviation + ' ', f'\x00{i}\x00 ')
    sentences = []
    for sentence in SENTENCE_END.split(protected):
        for i, abbreviation in enumerate(ABBREVIATIONS):
            sentence = sentence.replace(f'\x00{i}\x00', abbreviation)
        if sentence.strip():
            sentences.append(sentence.strip())
    return sentences


def segments(source, text):
    """unit document: the whole text is one segment, paragraphs and '## ' headings kept. unit sentence: one
    segment per sentence (headings skipped), with the sentences before and after it as context. seg_ids are
    <id>_1, <id>_2, ... in order."""
    paragraphs = [' '.join(paragraph.split()) for paragraph in text.split('\n\n') if paragraph.strip()]
    if source.unit == 'document':
        units = ['\n\n'.join(paragraphs)]
    else:
        units = [sentence for paragraph in paragraphs if not paragraph.startswith('## ')
                 for sentence in split_sentences(paragraph)]
    metadata = json.dumps(source.metadata, ensure_ascii=False, sort_keys=True)
    source_url = source.source_url or source.url
    return [Segment(seg_id=f'{source.id}_{i + 1}', src_lang=source.src_lang, tgt_lang=source.tgt_lang, text=unit,
                    context_before=units[i - 1] if i > 0 and source.unit == 'sentence' else '',
                    context_after=units[i + 1] if i + 1 < len(units) and source.unit == 'sentence' else '',
                    source_url=source_url, metadata=metadata)
            for i, unit in enumerate(units)]
