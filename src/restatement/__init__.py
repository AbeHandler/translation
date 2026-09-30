"""
How an English article restates the Chinese page it links to: translation, paraphrase, or neither.

For each (English article, Chinese page) pair found by the link queues:
    pages.py   the English article's citing paragraph (the <p> or block holding the link) and the sentence holding
               the link, and the Chinese page's main-text sentences (readability, so no menus)
    align.py   each citing sentence's closest Chinese sentences, by a multilingual sentence model built for
               finding translations (LaBSE), and a first label from the best score: over the whole paragraph
               (label) and over the sentence holding the link (anchor_label)
scripts/find_restatements.py runs it over a pairs file.
"""
