"""
TranslationStore: the MT queue and every translation call, in one SQLite database.

    queue   the segments waiting for MT, one row per seg_id: src_lang, tgt_lang, text, context_before,
            context_after, source (where it came from, e.g. the CSV), added_at. Rows stay after they are
            translated; "done" is worked out from calls, so adding an engine re-opens every segment for it.
    calls   one row per call, failed ones included: engine, model, context_mode, sample_idx, the segment,
            the text and prompt sent, temperature, translation (NULL on error), raw_response (JSON text, the
            engine's full response, kept so a run can be re-parsed or audited later), error, called_at,
            latency_ms, run_id, and call_key: a hash of what determines the call (engine, model,
            context_mode, sample_idx, source text, languages)
    runs    one row per run: run_id, started_at, settings (JSON)

A call_key with a successful row is cached: the runner never pays for it again. Failed calls are retried
on the next run and each attempt keeps its own row.
"""
import datetime
import hashlib
import json
import sqlite3

from src.translation.segments import Segment

SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
    seg_id TEXT PRIMARY KEY,
    src_lang TEXT NOT NULL,
    tgt_lang TEXT NOT NULL,
    text TEXT NOT NULL,
    context_before TEXT NOT NULL,
    context_after TEXT NOT NULL,
    source TEXT NOT NULL,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    settings TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY,
    call_key TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    seg_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    model TEXT NOT NULL,
    context_mode TEXT NOT NULL,
    sample_idx INTEGER NOT NULL,
    src_lang TEXT NOT NULL,
    tgt_lang TEXT NOT NULL,
    source_text TEXT NOT NULL,
    prompt TEXT NOT NULL,
    temperature REAL NOT NULL,
    translation TEXT,
    raw_response TEXT,
    error TEXT,
    called_at TEXT NOT NULL,
    latency_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS calls_call_key ON calls(call_key);
CREATE INDEX IF NOT EXISTS calls_seg_id ON calls(seg_id);
"""


def call_key(engine, model, context_mode, sample_idx, source_text, src_lang, tgt_lang):
    parts = [engine, model, context_mode, str(sample_idx), src_lang, tgt_lang, source_text]
    return hashlib.sha1('\x1f'.join(parts).encode('utf-8')).hexdigest()


class TranslationStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def enqueue(self, segments, source):
        """Add segments to the queue. A seg_id already queued with the same text is skipped; with different
        text it is an error (it would silently mix two texts under one id). Returns (added, already queued)."""
        queued = {row[0]: row[1:] for row in self.db.execute(
            'SELECT seg_id, src_lang, tgt_lang, text, context_before, context_after FROM queue')}
        added_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        new = []
        for s in segments:
            fields = (s.src_lang, s.tgt_lang, s.text, s.context_before, s.context_after)
            if s.seg_id not in queued:
                new.append((s.seg_id, *fields, source, added_at))
            elif queued[s.seg_id] != fields:
                raise ValueError(f'seg_id {s.seg_id} is already queued with different text or languages')
        with self.db:
            self.db.executemany('INSERT INTO queue VALUES (?, ?, ?, ?, ?, ?, ?, ?)', new)
        return len(new), len(segments) - len(new)

    def queued_segments(self):
        return [Segment(*row) for row in self.db.execute(
            'SELECT seg_id, src_lang, tgt_lang, text, context_before, context_after FROM queue ORDER BY seg_id')]

    def start_run(self, settings):
        run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        with self.db:
            self.db.execute('INSERT INTO runs VALUES (?, ?, ?)',
                            (run_id, datetime.datetime.now(datetime.timezone.utc).isoformat(), json.dumps(settings)))
        return run_id

    def succeeded_keys(self):
        return {key for (key,) in self.db.execute('SELECT DISTINCT call_key FROM calls WHERE error IS NULL')}

    def add_call(self, row):
        """row: a dict with every calls column but id; raw_response is a dict (stored as JSON) or None."""
        row = {**row, 'raw_response': None if row['raw_response'] is None
               else json.dumps(row['raw_response'], ensure_ascii=False)}
        columns = ', '.join(row)
        with self.db:  # committed per call, so an interrupted run keeps everything it paid for
            self.db.execute(f'INSERT INTO calls ({columns}) VALUES ({", ".join("?" * len(row))})', list(row.values()))

    def distinct_translations(self, context_mode='isolated'):
        """{seg_id: number of distinct successful translations across engines and samples}"""
        return dict(self.db.execute(
            'SELECT seg_id, COUNT(DISTINCT TRIM(translation)) FROM calls '
            'WHERE error IS NULL AND context_mode = ? GROUP BY seg_id ORDER BY seg_id', (context_mode,)))

    def close(self):
        self.db.close()
