"""
Paraphrase (indirect attribution) detection: a token-classification model trained on PolNeAR
(github.com/networkdynamics/PolNeAR). Each word is tagged as part of a Source (who), a Cue (said, argued,
believes...), the Content attributed to the source, or Out. Direct quotes, whose content is entirely inside
quotation marks, are left to src/quote_extraction and tagged Out here.

    polnear.py    read PolNeAR's text + brat .ann files into tagged paragraphs
    predict.py    ParaphraseDetector: raw text -> attributions (content, cue, source)

Encoding, training and word tagging are shared with src/quote_extraction, in src/token_tagging.
scripts/train_paraphrase_detector.py runs it from config/paraphrase_detection.yaml.
"""
