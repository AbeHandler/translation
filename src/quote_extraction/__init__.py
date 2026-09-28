"""
Direct-quote extraction and attribution: a token-classification model trained on DirectQuote
(github.com/THUNLP-MT/DirectQuote). Each word is tagged as part of a quotation whose speaker is before it
(LeftSpeaker), after it (RightSpeaker) or absent (Unknown), as part of a Speaker, or Out.

    data.py       read the CoNLL-style file (normalized to IOB2) and split it
    predict.py    QuoteExtractor: raw text -> quotes with their speakers

Encoding, training and word tagging are shared with src/paraphrase_detection, in src/token_tagging.

scripts/train_quote_extractor.py runs it from config/quote_extraction.yaml.
"""
