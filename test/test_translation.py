"""Run from the repo root: python -m pytest test/"""
import json

from src.translation.backends import Backend
from src.translation.runner import plan_calls, run_translations
from src.translation.segments import Segment
from src.translation.store import TranslationStore


class FakeEngine(Backend):
    def __init__(self, name, is_llm, fail=False):
        self.name, self.model, self.is_llm, self.fail = name, f'{name}-model', is_llm, fail
        self.n_requests = 0

    def request(self, text, src, tgt, context_mode='isolated', temperature=0.0):
        self.n_requests += 1
        return {'out': f'{self.name}:{text}'}

    def parse(self, raw):
        if self.fail:
            raise KeyError('translations')
        return raw['out']

    def prompt(self, text, src, tgt, context_mode='isolated'):
        return f'translate {text}' if self.is_llm else ''


SEGMENTS = [Segment('s1', 'en', 'zh', 'Hello.', context_before='Hi.', context_after='Bye.'),
            Segment('s2', 'en', 'zh', 'Frontier model.')]


def test_plan_samples_llms_and_keeps_nmt_isolated():
    nmt, llm = FakeEngine('nmt', False), FakeEngine('llm', True)
    calls = plan_calls(SEGMENTS, [nmt, llm], ['isolated', 'windowed'], n_samples=3)
    by = {(c.segment.seg_id, c.engine.name, c.context_mode) for c in calls}
    assert len(calls) == 2 * (1 + 3) + 3  # isolated: nmt once + llm x3 per segment; windowed: llm x3 for s1 only
    assert ('s1', 'nmt', 'windowed') not in by and ('s2', 'llm', 'windowed') not in by
    windowed = [c for c in calls if c.context_mode == 'windowed'][0]
    assert windowed.source_text == 'Hi. <<< Hello. >>> Bye.'


def test_rerun_skips_stored_calls(tmp_path):
    engine = FakeEngine('nmt', False)
    store = TranslationStore(str(tmp_path / 't.sqlite'))
    calls = plan_calls(SEGMENTS, [engine], ['isolated'], n_samples=1)
    counts = run_translations(calls, store, store.start_run({}), temperature=0.7, delay_seconds=0)
    assert counts['made'] == 2 and engine.n_requests == 2
    counts = run_translations(calls, store, store.start_run({}), temperature=0.7, delay_seconds=0)
    assert counts['made'] == 0 and counts['cached'] == 2 and engine.n_requests == 2
    rows = store.db.execute('SELECT seg_id, translation, temperature FROM calls ORDER BY seg_id').fetchall()
    assert rows == [('s1', 'nmt:Hello.', 0.0), ('s2', 'nmt:Frontier model.', 0.0)]


def test_parse_failure_keeps_raw_response_and_is_retried(tmp_path):
    engine = FakeEngine('nmt', False, fail=True)
    store = TranslationStore(str(tmp_path / 't.sqlite'))
    calls = plan_calls(SEGMENTS[:1], [engine], ['isolated'], n_samples=1)
    counts = run_translations(calls, store, store.start_run({}), temperature=0.7, delay_seconds=0)
    assert counts['errors'] == 1
    raw, error = store.db.execute('SELECT raw_response, error FROM calls').fetchone()
    assert json.loads(raw) == {'out': 'nmt:Hello.'} and error.startswith('KeyError')
    run_translations(calls, store, store.start_run({}), temperature=0.7, delay_seconds=0)
    assert engine.n_requests == 2  # a failed call isn't cached
