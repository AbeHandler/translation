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


def test_queue_skips_requeued_segments_and_rejects_changed_text(tmp_path):
    import pytest
    store = TranslationStore(str(tmp_path / 't.sqlite'))
    assert store.enqueue(SEGMENTS, 'a.csv') == (2, 0)
    assert store.enqueue(SEGMENTS, 'a.csv') == (0, 2)
    assert store.queued_segments() == SEGMENTS
    with pytest.raises(ValueError, match='different text'):
        store.enqueue([Segment('s1', 'en', 'zh', 'Changed.')], 'b.csv')


def test_run_queue_translates_everything_queued_once(tmp_path):
    from src.translation.runner import run_queue
    engine = FakeEngine('llm', True)
    store = TranslationStore(str(tmp_path / 't.sqlite'))
    store.enqueue(SEGMENTS, 'a.csv')
    _, counts = run_queue(store, [engine], ['isolated', 'windowed'], 2, 0.7, delay_seconds=0)
    assert counts['made'] == 2 * 2 + 2  # isolated x2 samples per segment; windowed x2 for s1
    store.enqueue([Segment('s3', 'en', 'zh', 'New.')], 'b.csv')
    _, counts = run_queue(store, [engine], ['isolated', 'windowed'], 2, 0.7, delay_seconds=0)
    assert counts['made'] == 2 and counts['cached'] == 6


def test_runner_lock_refuses_a_second_runner(tmp_path):
    import pytest
    from src.translation.runner import runner_lock
    lock = str(tmp_path / 't.sqlite.lock')
    with runner_lock(lock):
        with pytest.raises(RuntimeError, match='another MT runner'):
            with runner_lock(lock):
                pass
    with runner_lock(lock):  # released when the first runner ends
        pass


def test_csv_metadata_is_queued(tmp_path):
    from src.translation.segments import read_segments
    csv_path = tmp_path / 's.csv'
    csv_path.write_text('seg_id,src_lang,tgt_lang,text,source_url,author\n'
                        't1,en,zh,Once again.,https://www.ithome.com/1/006/510.htm,@TheStalwart\n', encoding='utf-8')
    store = TranslationStore(str(tmp_path / 'new_dir' / 't.sqlite'))  # creates the directory
    store.enqueue(read_segments(csv_path), 's.csv')
    (segment,) = store.queued_segments()
    assert segment.source_url == 'https://www.ithome.com/1/006/510.htm'
    assert json.loads(segment.metadata) == {'author': '@TheStalwart'}
