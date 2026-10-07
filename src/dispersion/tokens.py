"""Words with their character offsets, for word aligners: English by regex, Chinese by jieba (which keeps Latin runs
like "AI" or "GPT-4o" whole)."""
import re

WORD = re.compile(r"[A-Za-z0-9]+(?:[-'.][A-Za-z0-9]+)*|[^\sA-Za-z0-9]")


# AI terms jieba would otherwise cut up (智能体 -> 智能 + 体), on top of config/chinese_ai_terms.txt
EXTRA_ZH_WORDS = ['智能体', '大模型', '大语言模型', '多模态', '算力', '开源', '闭源', '对齐', '推理模型', '前沿模型',
                  '通用人工智能', '超级智能', '具身智能', '生成式人工智能', '人工智能治理', '出口管制', '蒸馏']
_jieba = None


def _zh_tokenizer():
    """jieba, taught the AI terms (once)."""
    global _jieba
    if _jieba is None:
        import jieba
        from src.ai_mentions import load_terms
        for word in [t for t in load_terms() if any('\u4e00' <= ch <= '\u9fff' for ch in t)] + EXTRA_ZH_WORDS:
            jieba.add_word(word, 100000)   # frequent enough to win over cutting it up
        _jieba = jieba
    return _jieba


def tokens(text, lang):
    """[(word, start, end)] of the text, spaces left out."""
    if lang == 'zh':
        return [(w, a, b) for w, a, b in _zh_tokenizer().tokenize(text) if w.strip()]
    return [(m.group(), m.start(), m.end()) for m in WORD.finditer(text)]


def merge_spans(spans, text):
    """Adjacent spans (only spaces between them) joined: aligned words -> the pieces of a rendering."""
    out = []
    for a, b in sorted(spans):
        if out and not text[out[-1][1]:a].strip():
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out
