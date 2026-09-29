"""
English and Chinese Wikipedia articles about AI, and the external links they cite. From the multistream dumps
(one pass over every article), in steps (scripts/wikipedia_pipeline.py):
    download  the dump and its index                          dump.py
    pages     every article whose wikitext says "AI", per chunk of the dump; the expensive pass, done once
    filter    the AI articles: a rule from config/wikipedia.yaml over those pages, cheap to change and rerun
    queue     the external links of the AI articles, as shards of 1000 {srcpage, url} lines, shuffled
                                                              links.py
"""
