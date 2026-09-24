"""
Machine translation of source segments by several engines, stored in one SQLite database.

    segments.py  Segment (seg_id, languages, text, context) and read_segments() from a CSV
    backends.py  one class per engine (Google NMT/LLM, Baidu, DeepL, OpenAI-compatible LLMs) + ENGINES
    store.py     TranslationStore: the SQLite database of every call, raw response included
    runner.py    run_translations(): the call plan, cached calls skipped, in random order

scripts/run_translations.py drives it.
"""
