"""The two sides of a pair: the English article's citing paragraph, and the Chinese page's sentences."""
import re
from urllib.parse import urljoin, urlparse

import lxml.html
from readability import Document

BLOCKS = ('p', 'li', 'blockquote', 'td', 'figcaption', 'h1', 'h2', 'h3', 'h4', 'div')
EN_SENTENCE_END = re.compile(r'(?:(?<=[.!?])|(?<=[.!?]["”’)\]]))\s+(?=[A-Z0-9"“‘(\[])')
ZH_SENTENCE_END = re.compile(r'(?<=[。！？!?])(?![”’」』）])|(?<=[。！？][”’」』）])')
MIN_ZH_CHARS = 8  # shorter "sentences" are menus, buttons, dates


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


def english_sentences(paragraph):
    return [s.strip() for s in EN_SENTENCE_END.split(paragraph) if s.strip()]


def anchor_sentence(paragraph, anchor_text):
    """The sentence of the paragraph that holds the link's text (the claim the link supports), or None."""
    for sentence in english_sentences(paragraph):
        if anchor_text and anchor_text in sentence:
            return sentence
    return None


def main_text(html):
    """The page's main content (readability), without menus and sidebars; the whole page if that fails."""
    try:
        text = lxml.html.fromstring(Document(html).summary()).text_content()
    except Exception:
        text = lxml.html.fromstring(html).text_content()
    return ' '.join(text.split())


def chinese_sentences(text):
    """The page text's sentences with at least MIN_ZH_CHARS Chinese characters."""
    sentences = []
    for part in ZH_SENTENCE_END.split(text):
        part = part.strip()
        if len(re.findall(r'[一-鿿]', part)) >= MIN_ZH_CHARS:
            sentences.append(part)
    return sentences
