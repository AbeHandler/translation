"""
Machine translation of queued source segments by every registered engine, in one SQLite database.

    sources.py   source documents (config/mt_sources.yaml): fetched, parsed each its own way, split into
                 segments
    segments.py  Segment: seg_id, languages, text, context, source_url, metadata
    backends.py  one class per engine (Google NMT/LLM, Baidu, DeepL, OpenAI-compatible LLMs) + ENGINES,
                 the registry
    store.py     TranslationStore: the MT queue, and every call with its raw response
    runner.py    the runner: run_queue() translates the whole queue, skipping calls already stored

scripts/run_translations.py runs it all as steps: fetch, queue, translate.
"""
