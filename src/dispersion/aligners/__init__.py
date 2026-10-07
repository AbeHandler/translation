"""Phrase aligners: given the focal phrase's span in a source sentence and the target sentence, the spans of the
target sentence that render it (offsets within that sentence; several when the target splits it), or [] if it
isn't rendered there. Each has .name and .align(focal_span, source_sentence, target_sentence) -> (spans, score)."""
