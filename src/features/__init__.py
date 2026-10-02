"""
Features of (English document, Chinese document) pairs for the transmission model (src/model/model1.py,
docs/model1.md). Each is weak evidence that the English document transmits the Chinese one:
    links        the English document links to the Chinese one (pairs.py)
    copying      it contains a run of Chinese characters from the Chinese one (copying.py)
    screenshots  it shows an image of the Chinese page (not built yet)
    similarity   their embeddings are similar (pairs.py, from vectors computed elsewhere)
    dates        they were published close together (pairs.py)
candidates.py mines the pairs to score: a pair enters the matrix if any feature fires (for now: links only).
"""
