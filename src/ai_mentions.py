"""The shared "is this about AI" rule: "AI" as a word of its own. Not inside other Latin words ("MAIL", "Aida",
"OpenAI"), but it may touch Chinese characters ("AI芯片"), so plain \\b word boundaries (which treat CJK as word
characters) aren't used. For HTML, count it in the page's visible text, after a cheap check on the raw bytes;
or only in the article body (mentions_ai_body: readability's main content, without menus, sidebars and "related
stories", which put "AI" on pages that aren't about it)."""
import re

AI = re.compile(r'(?<![A-Za-z])AI(?![A-Za-z])')
AI_BYTES = re.compile(rb'(?<![A-Za-z])AI(?![A-Za-z])')


def mentions_ai(text):
    """How many times "AI" appears as a word."""
    return len(AI.findall(text or ''))


def mentions_ai_html(html):
    """(times "AI" appears as a word in the page's visible text, that text). Pages whose raw bytes never
    contain "AI" aren't parsed; unparseable pages count as 0."""
    from src.link_language.fetch import visible_text  # lxml; imported here so plain-text users don't need it
    if isinstance(html, str):
        html = html.encode('utf-8', errors='replace')
    if not AI_BYTES.search(html):
        return 0, ''
    try:
        _, text = visible_text(html.decode('utf-8', errors='replace'))
    except Exception:
        return 0, ''
    return mentions_ai(text), text


def mentions_ai_body(html):
    """Times "AI" appears as a word in the article body (readability); 0 for unparseable pages."""
    import lxml.html  # imported here so plain-text users don't need them
    from readability import Document
    if isinstance(html, bytes):
        html = html.decode('utf-8', errors='replace')
    if not AI.search(html or ''):
        return 0
    try:
        return mentions_ai(lxml.html.fromstring(Document(html).summary()).text_content())
    except Exception:
        return 0


# Chinese pages: "AI" as above, or the Chinese terms for AI, large models, generative AI, compute and agents, or
# the best-known model names
AI_ZH = re.compile(r'(?<![A-Za-z])AI(?![A-Za-z])|人工智能|大模型|生成式|ChatGPT|DeepSeek|OpenAI|算力|智能体')


def about_ai(html):
    """True if the page's visible text mentions AI (in Chinese or English)."""
    import lxml.html  # imported here so plain-text users don't need it
    try:
        text = lxml.html.fromstring(html).text_content()
    except Exception:
        return False
    return bool(AI_ZH.search(text))
