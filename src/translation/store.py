"""
TranslationStore: the MT queue and every translation call, in one SQLite database.

    queue   the segments waiting for MT, one row per seg_id: src_lang, tgt_lang, text, context_before,
            context_after, source_url, metadata (JSON: author, published, ...), source (the file it was
            queued from), added_at. Rows stay after they are
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
import os
import sqlite3
from dataclasses import astuple, fields

from src.translation.segments import Segment

SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
    seg_id TEXT PRIMARY KEY,
    src_lang TEXT NOT NULL,
    tgt_lang TEXT NOT NULL,
    text TEXT NOT NULL,
    context_before TEXT NOT NULL,
    context_after TEXT NOT NULL,
    source_url TEXT NOT NULL,
    metadata TEXT NOT NULL,
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


SEGMENT_COLUMNS = ', '.join(field.name for field in fields(Segment))  # queue columns, in Segment's order


def call_key(engine, model, context_mode, sample_idx, source_text, src_lang, tgt_lang):
    parts = [engine, model, context_mode, str(sample_idx), src_lang, tgt_lang, source_text]
    return hashlib.sha1('\x1f'.join(parts).encode('utf-8')).hexdigest()


class TranslationStore:
    def __init__(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def enqueue(self, segments, source):
        """Add segments to the queue. A seg_id already queued identically is skipped; queued with anything
        different (text, languages, context, url, metadata) it is an error, since it would silently mix two
        sources under one id. Returns (added, already queued)."""
        queued = {row[0]: row for row in self.db.execute(f'SELECT {SEGMENT_COLUMNS} FROM queue')}
        added_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        new = []
        for s in segments:
            values = astuple(s)
            if s.seg_id not in queued:
                new.append((*values, source, added_at))
            elif queued[s.seg_id] != values:
                raise ValueError(f'seg_id {s.seg_id} is already queued with different text, languages or metadata')
        with self.db:
            self.db.executemany(f'INSERT INTO queue ({SEGMENT_COLUMNS}, source, added_at) '
                                f'VALUES ({", ".join("?" * (len(fields(Segment)) + 2))})', new)
        return len(new), len(segments) - len(new)

    def queued_segments(self):
        return [Segment(*row) for row in self.db.execute(f'SELECT {SEGMENT_COLUMNS} FROM queue ORDER BY seg_id')]

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
