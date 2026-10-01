"""
The news-similarity encoder of Litterer, Jurgens & Card (2023), "When it Rains, it Pours: Modeling Media Storms
and the News Ecosystem" (Findings of EMNLP): all-mpnet-base-v2 fine-tuned on the SemEval-2022 Task 8 article
pairs (https://huggingface.co/Blablablab/newsSimilarity). An article (headline + text) is read as its first
HEAD_TOKENS and last TAIL_TOKENS tokens, mean-pooled, and two articles' similarity is the cosine of their
vectors; the paper links articles above 0.9 into story clusters.

The weights are one file, state_dict.tar (~440MB), fetched once by ensure_weights().
"""
import os
import urllib.request

import numpy as np
import torch
from transformers import AutoConfig, AutoModel, AutoTokenizer

BASE_MODEL = 'sentence-transformers/all-mpnet-base-v2'
WEIGHTS_URL = 'https://huggingface.co/Blablablab/newsSimilarity/resolve/main/state_dict.tar'
HEAD_TOKENS, TAIL_TOKENS = 288, 96  # the paper's head + tail; 384 is the base model's maximum


def ensure_weights(path):
    """Download state_dict.tar to path unless it is there. Via a per-process .part file renamed into place, so
    workers starting together never read a partial download (the last identical copy wins)."""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        part = f'{path}.{os.getpid()}.part'
        urllib.request.urlretrieve(WEIGHTS_URL, part)
        os.rename(part, path)
    return path


class _Wrapped(torch.nn.Module):
    """The module the weights were saved from: its keys are model.<mpnet parameter>."""

    def __init__(self):
        super().__init__()
        self.model = AutoModel.from_config(AutoConfig.from_pretrained(BASE_MODEL))  # weights come from state_dict


class NewsSimilarityEncoder:
    def __init__(self, weights_path, batch_size=16):
        state = torch.load(weights_path, map_location='cpu')
        state.pop('model.embeddings.position_ids', None)  # a buffer newer transformers don't keep
        wrapped = _Wrapped()
        wrapped.load_state_dict(state)
        self.model = wrapped.model.eval()
        self.tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, model_max_length=10 ** 6)  # we cut head + tail
        self.batch_size = batch_size

    def token_ids(self, text):
        """The text's first HEAD_TOKENS - 1 and last TAIL_TOKENS - 1 tokens, between <s> and </s> (384 in all)."""
        ids = self.tokenizer(text, add_special_tokens=False, truncation=False)['input_ids']
        head, tail = HEAD_TOKENS - 1, TAIL_TOKENS - 1
        if len(ids) > head + tail:
            ids = ids[:head] + ids[-tail:]
        return [self.tokenizer.cls_token_id] + ids + [self.tokenizer.sep_token_id]

    @torch.no_grad()
    def encode(self, texts):
        """Unit-length float32 vectors, one row per text (cosine similarity = dot product)."""
        out = []
        for start in range(0, len(texts), self.batch_size):
            batch = [self.token_ids(text) for text in texts[start:start + self.batch_size]]
            padded = self.tokenizer.pad({'input_ids': batch}, return_tensors='pt')
            hidden = self.model(**padded).last_hidden_state
            mask = padded['attention_mask'].unsqueeze(-1).float()
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            out.append(torch.nn.functional.normalize(pooled, dim=1).numpy())
        return np.concatenate(out) if out else np.zeros((0, 768), dtype=np.float32)
