"""
The quote-around-link feature: the English document puts its link to the Chinese document in quotation marks,
“<a>umbrella governance</a>” or <a>“interim measures”</a>, a sign it is rendering the source's own words. The
marks are usually just outside the <a> tag, so the anchor is looked up in its paragraph (the citing paragraphs of
src/restatement/pages.py) and the characters around it are checked.
"""
OPENING = '"“‘\'「『«'
CLOSING = '"”’\'」』»'


def quoted_anchor(paragraph, anchor_text):
    """1 if anchor_text is in quotation marks in paragraph (marks inside the anchor, or right around it), 0 if
    not, -1 if the anchor isn't found in the paragraph."""
    anchor = (anchor_text or '').strip()
    if not anchor:
        return -1
    if anchor[0] in OPENING and anchor[-1] in CLOSING:
        return 1
    start = (paragraph or '').find(anchor)
    if start < 0:
        return -1
    before = paragraph[:start].rstrip()[-1:]
    after = paragraph[start + len(anchor):].lstrip()[:1]
    return int(bool(before) and before in OPENING and bool(after) and after in CLOSING)


def link_quoted(citing):
    """Feature value for one link from its citing paragraphs ([{paragraph, anchor_text}]): 1 if any occurrence is
    quoted, 0 if found but none are, -1 if none are found."""
    values = [quoted_anchor(c['paragraph'], c['anchor_text']) for c in citing]
    return max(values) if values else -1
