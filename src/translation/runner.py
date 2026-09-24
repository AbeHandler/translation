"""run_translations(): every (segment, context mode, engine, sample) call not already in the store, in random
order, each stored as it completes (src/translation/store.py). The random order means a run stopped early
still leaves an unbiased sample across segments and engines."""
import datetime
import logging
import random
import time
from dataclasses import dataclass

from src.translation.store import call_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Call:
    segment: object
    engine: object
    context_mode: str
    sample_idx: int

    @property
    def source_text(self):
        return self.segment.source_text(self.context_mode)

    @property
    def key(self):
        return call_key(self.engine.name, self.engine.model, self.context_mode, self.sample_idx,
                        self.source_text, self.segment.src_lang, self.segment.tgt_lang)


def plan_calls(segments, engines, context_modes, n_samples):
    """LLMs get n_samples per segment and mode; NMT engines one, and isolated sentences only (they can't be
    asked for just the marked sentence). windowed is skipped for segments with no context."""
    calls = []
    for segment in segments:
        for context_mode in context_modes:
            if context_mode == 'windowed' and not segment.has_context:
                continue
            for engine in engines:
                if context_mode == 'windowed' and not engine.is_llm:
                    continue
                for sample_idx in range(n_samples if engine.is_llm else 1):
                    calls.append(Call(segment, engine, context_mode, sample_idx))
    return calls


def run_translations(calls, store, run_id, temperature, delay_seconds=0.4):
    """Make every call whose key has no successful row yet. Returns counts."""
    done = store.succeeded_keys()
    todo = [call for call in calls if call.key not in done]
    random.shuffle(todo)
    logger.info('%d calls planned, %d already stored, %d to make', len(calls), len(calls) - len(todo), len(todo))
    counts = {'planned': len(calls), 'cached': len(calls) - len(todo), 'made': 0, 'errors': 0}
    for call in todo:
        store.add_call(make_call(call, run_id, temperature))
        counts['made'] += 1
        time.sleep(delay_seconds)
    counts['errors'] = store.db.execute('SELECT COUNT(*) FROM calls WHERE run_id = ? AND error IS NOT NULL',
                                        (run_id,)).fetchone()[0]
    return counts


def make_call(call, run_id, temperature):
    """One engine call as a calls row. The raw response is kept even when parsing it fails."""
    segment, engine = call.segment, call.engine
    temperature = temperature if engine.is_llm else 0.0
    row = {'call_key': call.key, 'run_id': run_id, 'seg_id': segment.seg_id, 'engine': engine.name,
           'model': engine.model, 'context_mode': call.context_mode, 'sample_idx': call.sample_idx,
           'src_lang': segment.src_lang, 'tgt_lang': segment.tgt_lang, 'source_text': call.source_text,
           'prompt': engine.prompt(call.source_text, segment.src_lang, segment.tgt_lang, call.context_mode),
           'temperature': temperature, 'translation': None, 'raw_response': None, 'error': None,
           'called_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    started = time.time()
    try:
        row['raw_response'] = engine.request(call.source_text, segment.src_lang, segment.tgt_lang,
                                             call.context_mode, temperature)
        row['translation'] = engine.parse(row['raw_response'])
    except Exception as exc:  # stored, not raised: one bad call shouldn't stop a paid run; retried next run
        row['error'] = f'{type(exc).__name__}: {exc}'[:1000]
        logger.error('%s/%s/%s/%d: %s', engine.name, segment.seg_id, call.context_mode, call.sample_idx, row['error'])
    row['latency_ms'] = int((time.time() - started) * 1000)
    return row
