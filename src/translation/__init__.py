"""
Machine translation of queued source segments by every registered engine, in one SQLite database.

    segments.py  Segment (seg_id, languages, text, context) and read_segments() from a CSV
    backends.py  one class per engine (Google NMT/LLM, Baidu, DeepL, OpenAI-compatible LLMs) + ENGINES,
                 the registry
    store.py     TranslationStore: the MT queue, and every call with its raw response
    runner.py    the runner: run_queue() translates the whole queue, skipping calls already stored

scripts/enqueue_segments.py adds to the queue; scripts/run_translations.py starts the runner.
"""
