"""A word aligner (SimAlign: Jalili Sabet et al. 2020): words aligned by the similarity of their contextual
embeddings in a multilingual model, no training needed. The focal phrase's words are aligned to target words; the
target words, merged where adjacent, are the rendering (several pieces when the target splits it). Free and local,
but noisy on idioms and loose paraphrase. The model (mBERT by default, ~700 MB) is downloaded once."""
from src.dispersion.tokens import merge_spans, tokens

METHOD = 'itermax'    # SimAlign's alignment method: 'inter' (precise), 'itermax' (more recall), 'mwmf'
METHOD_CODES = {'itermax': 'i', 'inter': 'a', 'mwmf': 'm'}


class SimAlignAligner:
    name = 'simalign'

    def __init__(self, source_lang, target_lang, model='bert', method=METHOD, aligner=None):
        self.source_lang, self.target_lang, self.method = source_lang, target_lang, method
        if aligner is None:
            from simalign import SentenceAligner
            aligner = SentenceAligner(model=model, token_type='bpe', matching_methods=METHOD_CODES[method])
        self.aligner = aligner

    def align(self, focal_span, source_sentence, target_sentence):
        src, tgt = tokens(source_sentence, self.source_lang), tokens(target_sentence, self.target_lang)
        focal = {i for i, (_, a, b) in enumerate(src) if a < focal_span[1] and focal_span[0] < b}
        if not focal or not tgt:
            return [], 0.0
        pairs = self.aligner.get_word_aligns([w for w, _, _ in src], [w for w, _, _ in tgt])[self.method]
        hit = {j for i, j in pairs if i in focal}
        aligned_focal = {i for i, j in pairs if i in focal}
        spans = merge_spans([(tgt[j][1], tgt[j][2]) for j in hit], target_sentence)
        return spans, len(aligned_focal) / len(focal)
