"""
What kind of image is this? Zero-shot classification with CLIP (clip-ViT-B-32 through sentence-transformers;
free, local, CPU): an image's class is the description it is most similar to. For finding English screenshots
(tweets, web pages) in Chinese articles; reading them is a later OCR step. Logic only.

Also: pulling an article's body images out of its HTML (readability, so logos and sidebars are left out),
fetching them into memory with the article as Referer (many Chinese image hosts refuse requests without one), and
screen_article(): a high-recall pass over one article that keeps a small row per image (never the image itself):
its class, and, for anything that may be a screenshot of text, the OCR'd text and its share of Latin letters.
"""
import io
from urllib.parse import urljoin

import lxml.html
import numpy as np
from PIL import Image
from readability import Document

MODEL = 'clip-ViT-B-32'
CLASSES = {
    'tweet': 'a screenshot of a tweet on Twitter or X',
    'social_post': 'a screenshot of a social media post with comments',
    'web_page': 'a screenshot of a news article or web page with text',
    'document': 'a screenshot of a document, paper or announcement with paragraphs of text',
    'chart': 'a chart, graph or table of numbers',
    'photo': 'a photograph of people, places or objects',
    'product': 'a product photo or advertisement',
    'logo': 'a logo or icon',
}
TEXT_CLASSES = ('tweet', 'social_post', 'web_page', 'document')   # screenshots of text: OCR'd
TEXT_RECALL = 0.25   # high recall: OCR an image if these classes together have at least this probability
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
    """The image's text, by Tesseract (free, local; needs its eng and chi_sim language files, TESSDATA_PREFIX)."""
    import pytesseract
    return ' '.join(pytesseract.image_to_string(image, lang=langs).split())


def latin_share(text):
    letters = [ch for ch in text if ch.isalpha()]
    return sum(ch.isascii() for ch in letters) / len(letters) if letters else 0.0


def screen_article(html, page_url, client, classifier, ocr=None, max_images=40):
    """[{page, src, alt, width, height, label, score, text_prob, ocr_text, latin}] for the article's body images:
    each is fetched into memory, classified, OCR'd (ocr(image) -> text, if given) when the text-screenshot
    classes together reach TEXT_RECALL, and dropped. Images that can't be fetched get label None."""
    rows, images = [], []
    for img in body_images(html, page_url)[:max_images]:
        image = fetch_image(img['src'], page_url, client)
        rows.append({'page': page_url, 'src': img['src'], 'alt': img['alt'], 'width': None, 'height': None,
                     'label': None, 'score': None, 'text_prob': None, 'ocr_text': None, 'latin': None})
        images.append(image)
    fetched = [i for i, image in enumerate(images) if image is not None]
    for i, (label, score, scores) in zip(fetched, classifier.classify([images[i] for i in fetched])):
        text_prob = sum(scores[c] for c in TEXT_CLASSES)
        rows[i].update(width=images[i].size[0], height=images[i].size[1], label=label, score=round(score, 3),
                       text_prob=round(text_prob, 3))
        if ocr and text_prob >= TEXT_RECALL:
            text = ocr(images[i])
            rows[i].update(ocr_text=text, latin=round(latin_share(text), 3))
    return rows
