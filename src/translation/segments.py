"""A segment: one unit of source text to translate (usually a sentence), with its neighbouring sentences
as context and where it came from. src/translation/sources.py makes them from source documents."""
from dataclasses import dataclass

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
