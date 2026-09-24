"""Source segments to translate, read from a CSV with columns
    seg_id, src_lang, tgt_lang, text          required
    context_before, context_after             optional: the neighbouring sentences, for windowed mode
    source_url                                optional: where the text was found
    any other column                          kept as metadata (e.g. author, published), as JSON
"""
import csv
import json
from dataclasses import dataclass

REQUIRED_COLUMNS = {'seg_id', 'src_lang', 'tgt_lang', 'text'}
KNOWN_COLUMNS = REQUIRED_COLUMNS | {'context_before', 'context_after', 'source_url'}
CONTEXT_MODES = ('isolated', 'windowed')


@dataclass(frozen=True)
class Segment:
    seg_id: str
    src_lang: str
    tgt_lang: str
    text: str
    context_before: str = ''
    context_after: str = ''
    source_url: str = ''
    metadata: str = '{}'  # JSON object, as a string so a Segment stays immutable

    @property
    def has_context(self):
        return bool(self.context_before or self.context_after)

    def source_text(self, context_mode):
        """isolated: the sentence alone. windowed: the sentence marked <<< >>> inside its neighbours."""
        if context_mode == 'isolated':
            return self.text
        if context_mode == 'windowed':
            return f'{self.context_before} <<< {self.text} >>> {self.context_after}'.strip()
        raise ValueError(f'context_mode must be one of {CONTEXT_MODES}, not {context_mode!r}')


def read_segments(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f'no rows in {path}')
    missing = REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise ValueError(f'{path} is missing columns: {", ".join(sorted(missing))}')
    seg_ids = [row['seg_id'] for row in rows]
    if len(set(seg_ids)) != len(seg_ids):
        raise ValueError(f'{path} has duplicate seg_ids')
    return [Segment(seg_id=row['seg_id'], src_lang=row['src_lang'], tgt_lang=row['tgt_lang'],
                    text=row['text'].strip(), context_before=(row.get('context_before') or '').strip(),
                    context_after=(row.get('context_after') or '').strip(),
                    source_url=(row.get('source_url') or '').strip(),
                    metadata=json.dumps({k: v for k, v in row.items() if k not in KNOWN_COLUMNS and v},
                                        ensure_ascii=False, sort_keys=True))
            for row in rows]
