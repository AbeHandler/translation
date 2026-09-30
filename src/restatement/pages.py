"""The two sides of a pair: the English article's sentences (and the citing paragraph), and the Chinese page's."""
import re
from urllib.parse import urljoin, urlparse

import lxml.html
from readability import Document

BLOCKS = ('p', 'li', 'blockquote', 'td', 'figcaption', 'h1', 'h2', 'h3', 'h4', 'div')
LINE_BREAKS = BLOCKS + ('br', 'tr', 'h5', 'h6', 'section', 'article')
EN_SENTENCE_END = re.compile(r'(?:(?<=[.!?])|(?<=[.!?]["”’)\]]))\s+(?=[A-Z0-9"“‘(\[])')
ZH_SENTENCE_END = re.compile(r'(?<=[。！？!?])(?![”’」』）])|(?<=[。！？][”’」』）])')
MIN_ZH_CHARS = 8  # shorter "sentences" are menus, buttons, dates
MIN_EN_WORDS = 5  # shorter ones are bylines, names, "Copyright © 2026 ACN Newswire."


def same_url(a, b):
    """Same page, ignoring scheme, www., trailing slash and fragment."""
    def norm(url):
        parsed = urlparse(url)
        return (parsed.hostname or '').removeprefix('www.'), parsed.path.rstrip('/'), parsed.query
    return norm(a) == norm(b)


def citing_paragraphs(html, page_url, target_url):
    """[{paragraph, anchor_text}] for each link to target_url in the page: the text of the nearest enclosing
    block (a <p>, list item, quote, ...), so the claim the link supports is in it."""
    doc = lxml.html.fromstring(html)
    for node in doc.xpath('//script|//style|//noscript|//nav|//footer|//header'):
        node.drop_tree()
    found = []
    for anchor in doc.iter('a'):
        href = anchor.get('href')
        if not href or not same_url(urljoin(page_url, href), target_url):
            continue
        block = anchor
        while block.getparent() is not None and block.tag not in BLOCKS:
            block = block.getparent()
        paragraph = ' '.join(block.text_content().split())
        if paragraph and paragraph not in (f['paragraph'] for f in found):
            found.append({'paragraph': paragraph, 'anchor_text': ' '.join(anchor.text_content().split())})
    return found


def han_count(text):
    return len(re.findall(r'[一-鿿]', text))


def english_sentences(text):
    """The text's sentences of at least MIN_EN_WORDS words, one line at a time (lines are blocks, see
    block_text). Sentences with MIN_ZH_CHARS or more Chinese characters are dropped: Chinese quoted on the
    English page is not a restatement."""
    return [s.strip() for line in text.split('\n') for s in EN_SENTENCE_END.split(line)
            if len(s.split()) >= MIN_EN_WORDS and han_count(s) < MIN_ZH_CHARS]


def anchor_sentence(paragraph, anchor_text):
    """The sentence of the paragraph that holds the link's text (the claim the link supports), or None."""
    for sentence in english_sentences(paragraph):
        if anchor_text and anchor_text in sentence:
            return sentence
    return None


def block_text(element):
    """The element's text with one line per block (paragraph, list item, table row, ...), so text from
    neighbouring blocks is not glued into one sentence ("annoying.With Qoder")."""
    for node in element.xpath('.//script|.//style|.//noscript'):
        node.drop_tree()
    for node in element.iter(*LINE_BREAKS):
        node.tail = '\n' + (node.tail or '')
    lines = (' '.join(line.split()) for line in element.text_content().split('\n'))
    return '\n'.join(line for line in lines if line)


def readable_text(html):
    """The page's main content (readability), without menus and sidebars; '' when readability fails."""
    try:
        return block_text(lxml.html.fromstring(Document(html).summary()))
    except Exception:
        return ''


MIN_MAIN_SENTENCES = 5


def main_text(html):
    """The Chinese page's main content. Falls back to all the page's text when readability keeps fewer than
    MIN_MAIN_SENTENCES Chinese sentences (e.g. the Taiwan presidential gazette, whose text readability drops)."""
    text = readable_text(html)
    if len(chinese_sentences(text)) < MIN_MAIN_SENTENCES:
        doc = lxml.html.fromstring(html)
        text = block_text(doc.find('body') if doc.find('body') is not None else doc)
    return text


def chinese_sentences(text):
    """The text's sentences with at least MIN_ZH_CHARS Chinese characters, one line at a time."""
    sentences = []
    for line in text.split('\n'):
        for part in ZH_SENTENCE_END.split(line):
            part = part.strip()
            if han_count(part) >= MIN_ZH_CHARS:
                sentences.append(part)
    return sentences
