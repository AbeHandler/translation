"""
Word-level tagging with a fine-tuned token-classification model, shared by src/quote_extraction (direct quotes,
DirectQuote) and src/paraphrase_detection (indirect attributions, PolNeAR). Each word gets one IOB2 tag.

    data.py       Paragraph (words + tags), IOB2 normalization
    encoding.py   label map; word tags -> subword labels
    training.py   fine-tune and evaluate (HF Trainer, seqeval); write the model and its report
    tagger.py     words and paragraphs of raw text; WordTagger: words -> predicted tags; tags -> spans
"""
