"""A dictionary aligner: known renderings of each focal phrase, found in the target sentence. Transparent and
cheap, but only finds what it was told (governance -> 治理, 管控, 监管)."""
import re


class DictionaryAligner:
    name = 'dictionary'

    def __init__(self, renderings):
        self.renderings = {k.lower(): sorted(v, key=len, reverse=True) for k, v in renderings.items()}

    def align(self, focal_span, source_sentence, target_sentence):
        focal_text = source_sentence[focal_span[0]:focal_span[1]]
        for rendering in self.renderings.get(focal_text.lower(), []):
            m = re.search(re.escape(rendering), target_sentence, re.IGNORECASE)
            if m:
                return [(m.start(), m.end())], 1.0
        return [], 0.0
