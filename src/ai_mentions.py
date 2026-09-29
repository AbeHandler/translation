"""The shared "is this about AI" rule: "AI" as a word of its own. Not inside other Latin words ("MAIL", "Aida",
"OpenAI"), but it may touch Chinese characters ("AI芯片"), so plain \\b word boundaries (which treat CJK as word
characters) aren't used."""
import re

AI = re.compile(r'(?<![A-Za-z])AI(?![A-Za-z])')


def mentions_ai(text):
    """How many times "AI" appears as a word."""
    return len(AI.findall(text or ''))
