"""
What kind of image is this? Zero-shot classification with CLIP (clip-ViT-B-32 through sentence-transformers;
free, local, CPU): an image's class is the description it is most similar to. For finding English screenshots
(posts, web pages) in Chinese articles; reading them is a later OCR step. Logic only.

Also: pulling an article's body images out of its HTML (readability, so logos and sidebars are left out),
fetching them into memory with the article as Referer (many Chinese image hosts refuse requests without one), and
screen_article(): a high-recall pass over one article that keeps a small row per image (never the image itself):
its class, and, for anything that may be a screenshot of text, the OCR'd text and its share of Latin letters.
"""
import io
import json
import os
import re
from urllib.parse import urljoin

import lxml.html
import numpy as np
import pyarrow.parquet as pq
from PIL import Image
from readability import Document

from src.ai_mentions import about_ai

MODEL = 'clip-ViT-B-32'
CLASSES = {   # two text classes, and two that pull non-text images away (zero-shot scores compete)
    'post': 'a screenshot of a social media post or tweet',
    'page': 'a screenshot of a web page, article or document with text',
    'photo': 'a photograph of people, places or objects',
    'graphic': 'a chart, logo, icon or advertisement',
}
TEXT_CLASSES = ('post', 'page')   # screenshots of text: OCR'd
TEXT_RECALL = 0.25   # high recall: OCR an image if these classes together have at least this probability
# An English screenshot is mostly Latin text read with confidence (OCR noise like "mse Tid dad AAA" is read at ~30),
# and either a post with an @handle (a tweet: kopite7kimi's spec list has no sentences) or English prose: a news
# page, paper or statement. Prose is told from English interfaces, menus, charts and product pages (a DARPA org
# chart, an Amazon listing, a dashboard) by its function words: 20-36% of the words of real articles, 0-11% of UIs.
ENGLISH_MIN_LATIN, ENGLISH_MIN_CONF = 0.6, 70
ENGLISH_WORD = re.compile(r'(?<![A-Za-z])[A-Za-z]{3,}(?![A-Za-z])')
HANDLE = re.compile(r'@\s?\w{2,}')        # OCR may split it: "Eric Trump @ Se)"
PROSE_WORD = re.compile(r"[A-Za-z][A-Za-z']+")
FUNCTION_WORDS = set('the of and to a in is for that on with as by from at are was be this it an or we you they he '
                     'she has have not but will can its their our your'.split())
PROSE_MIN_WORDS, PROSE_MIN_FUNCTION, PROSE_MIN_SHARE = 8, 3, 0.18
MIN_SIDE = 200                     # images smaller than this (icons, spacers, avatars) are skipped
HEADERS = {'User-Agent': 'Mozilla/5.0 (research crawler; abha4861@colorado.edu)'}


def body_images(html, page_url):
    """[{src, alt}] of the images in the article body, absolute URLs, each once."""
    try:
        body = lxml.html.fromstring(Document(html.replace('\x00', '')).summary())
    except Exception:
        return []
    seen, out = set(), []
    for img in body.iter('img'):
        src = img.get('data-src') or img.get('data-original') or img.get('src') or ''
        if not src or src.startswith('data:'):
            continue
        src = urljoin(page_url, src)
        if src not in seen:
            seen.add(src)
            out.append({'src': src, 'alt': (img.get('alt') or '').strip()})
    return out


def fetch_image(src, page_url, client):
    """The image (PIL, RGB), or None if it can't be fetched or decoded, or is smaller than MIN_SIDE."""
    try:
        response = client.get(src, headers={**HEADERS, 'Referer': page_url}, follow_redirects=True, timeout=20)
        if response.status_code != 200:
            return None
        image = Image.open(io.BytesIO(response.content)).convert('RGB')
        image.info.pop('transparency', None)   # left over from palette PNGs; breaks saving it for Tesseract
    except Exception:
        return None
    return image if min(image.size) >= MIN_SIDE else None


class ImageClassifier:
    def __init__(self, model=None, classes=CLASSES):
        if model is None:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(MODEL, device='cpu')
        self.model = model
        self.names = list(classes)
        self.text = model.encode(list(classes.values()), normalize_embeddings=True)

    def classify(self, images):
        """[(class, score, {class: score})] per image; scores are softmaxed cosines (CLIP's scale of 100)."""
        if not images:
            return []
        vecs = self.model.encode(images, normalize_embeddings=True, batch_size=16)
        logits = 100 * vecs @ self.text.T
        probs = np.exp(logits - logits.max(1, keepdims=True))
        probs /= probs.sum(1, keepdims=True)
        return [(self.names[int(p.argmax())], float(p.max()), dict(zip(self.names, map(float, p)))) for p in probs]


def tesseract_ocr(image, langs='eng+chi_sim'):
    """(text, latin_conf): the image's text by Tesseract (free, local; needs its eng and chi_sim language files,
    TESSDATA_PREFIX), and Tesseract's mean confidence (0-100) in the words of 3+ Latin letters it read (0 if none):
    real English is read with high confidence, noise from a Chinese image or a photo is not."""
    import pytesseract
    data = pytesseract.image_to_data(image, lang=langs, output_type=pytesseract.Output.DICT)
    words = [(w, float(c)) for w, c in zip(data['text'], data['conf']) if w.strip()]
    latin = [c for w, c in words if ENGLISH_WORD.search(w) and c >= 0]
    return ' '.join(w for w, _ in words), (sum(latin) / len(latin) if latin else 0.0)


def is_prose(text):
    """Enough words, and enough of them function words (the, of, to, ...), as in sentences, not menus or labels."""
    words = [w.lower() for w in PROSE_WORD.findall(text)]
    function = sum(w in FUNCTION_WORDS for w in words)
    return len(words) >= PROSE_MIN_WORDS and function >= PROSE_MIN_FUNCTION and function / len(words) >= PROSE_MIN_SHARE


def english_kind(text, label, latin_conf=100.0):
    """'tweet', 'prose' or None: what kind of English screenshot an image is, from its CLIP label and OCR text."""
    if label not in TEXT_CLASSES or latin_share(text) < ENGLISH_MIN_LATIN or latin_conf < ENGLISH_MIN_CONF:
        return None
    if label == 'post' and HANDLE.search(text):
        return 'tweet'
    return 'prose' if is_prose(text) else None


def latin_share(text):
    letters = [ch for ch in text if ch.isalpha()]
    return sum(ch.isascii() for ch in letters) / len(letters) if letters else 0.0


def screen_article(html, page_url, client, classifier, ocr=None, max_images=40):
    """[{page, src, alt, width, height, label, score, text_prob, ocr_text, latin, english_screenshot}] for the
    article's body images (src: the image's URL; the image itself is never saved): each is fetched into memory,
    classified, OCR'd (ocr(image) -> (text, latin_conf), if given) when the text-screenshot classes together reach
    TEXT_RECALL, and dropped. Images that can't be fetched get label None.

    Important. Do not save or store images. Too much storage. Stream and classify. 10/2/26
    """
    rows, images = [], []
    for img in body_images(html, page_url)[:max_images]:
        image = fetch_image(img['src'], page_url, client)
        rows.append({'page': page_url, 'src': img['src'], 'alt': img['alt'], 'width': None, 'height': None,
                     'label': None, 'score': None, 'text_prob': None, 'ocr_text': None, 'latin': None,
                     'latin_conf': None, 'english_kind': None,
                     'english_screenshot': False})
        images.append(image)
    fetched = [i for i, image in enumerate(images) if image is not None]
    labelled = classifier.classify([images[i] for i in fetched]) if fetched else []
    for i, (label, score, scores) in zip(fetched, labelled):
        text_prob = sum(scores[c] for c in TEXT_CLASSES)
        rows[i].update(width=images[i].size[0], height=images[i].size[1], label=label, score=round(score, 3),
                       text_prob=round(text_prob, 3))
        if ocr and text_prob >= TEXT_RECALL:
            try:
                text, conf = ocr(images[i])
            except Exception as exc:   # one unreadable image shouldn't lose the whole file: recorded, not skipped
                rows[i]['ocr_error'] = f'{type(exc).__name__}: {exc}'[:200]
                continue
            kind = english_kind(text, label, conf)
            rows[i].update(ocr_text=text, latin=round(latin_share(text), 3), latin_conf=round(conf, 1),
                           english_kind=kind, english_screenshot=kind is not None)
    return rows


def screen_html_file(html_path, out_path, classifier, ocr, client, ai_only=True):
    """Screen the images of every page in a crawl's HTML Parquet file (the scrapy crawls' html/<part>.parquet)
    whose text is about AI; write one JSONL row per page {url, n_images, n_english_screenshots, images} (image
    URLs and their screening, never the images) via .part. Returns counts."""
    n_pages = n_screened = n_english = 0
    with open(out_path + '.part', 'w', encoding='utf-8') as f:
        for batch in pq.ParquetFile(html_path).iter_batches(batch_size=50, columns=['url', 'html']):
            for page in batch.to_pylist():
                n_pages += 1
                html = page['html'].decode('utf-8', errors='replace') if isinstance(page['html'], bytes) \
                    else page['html']
                if not html or (ai_only and not about_ai(html)):
                    continue
                images = screen_article(html, page['url'], client, classifier, ocr)
                english = sum(i['english_screenshot'] for i in images)
                n_screened, n_english = n_screened + 1, n_english + english
                f.write(json.dumps({'url': page['url'], 'n_images': len(images), 'n_english_screenshots': english,
                                    'images': images}, ensure_ascii=False) + '\n')
    os.rename(out_path + '.part', out_path)
    return {'pages': n_pages, 'screened': n_screened, 'english_screenshots': n_english}


def rescore_row(row):
    """Apply the current English test to a screened page's saved OCR (no fetching, no OCR): updates each image's
    english_kind and english_screenshot, and the page's n_english_screenshots. Returns the row."""
    for image in row['images']:
        if image.get('ocr_text') is not None:
            kind = english_kind(image['ocr_text'], image['label'], image.get('latin_conf') or 0.0)
            image['english_kind'], image['english_screenshot'] = kind, kind is not None
    row['n_english_screenshots'] = sum(bool(i.get('english_screenshot')) for i in row['images'])
    return row
