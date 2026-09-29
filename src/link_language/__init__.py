"""
The language of a linked page, for finding cross-language citations (English sources citing Chinese pages, and
the other way round). A row processor for the shard queue (src/shard_queue):

    fetch.py     fetch_page(url): status, final url, content type, title and visible text (first MAX_BYTES only)
    script.py    label_text(text): by writing system. The share of Han characters among letters decides zh vs a
                 Latin-script language; kana means ja, hangul ko; only the ambiguous middle goes to langdetect.
    labeler.py   LinkLanguageLabeler(cache_dir).label(row): fetch + label, with a cache per host shared by all
                 workers: once a host's first pages agree on a language, its other links are labelled without
                 fetching (label_source "host_cache").
"""
