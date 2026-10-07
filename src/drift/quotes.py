"""Is a rendering presented as a quotation? Spans inside quotation marks in a text (Chinese 「」『』“” and English
"" ''), so a rendering inside one can be flagged: words put in someone's mouth, whose meaning may have changed."""
import re

QUOTE = re.compile(r'「([^」]*)」|『([^』]*)』|“([^”]*)”|"([^"]*)"')


def quoted_spans(text):
    """[(start, end)] of the text inside quotation marks (the marks left out)."""
    return [(m.start(i), m.end(i)) for m in QUOTE.finditer(text) for i in range(1, 5) if m.group(i) is not None]


def is_quoted(span, text):
    """True if the span lies inside a quotation in the text."""
    return any(a <= span[0] and span[1] <= b for a, b in quoted_spans(text))
