"""
LLMDrift: a language model rates how faithfully a rendering carries a source passage, as in MT evaluation: a 1-5
faithfulness score (Likert), the kind of change (the same kinds as NLIDrift), what changed, and its direction (risk
or opportunity, competition or cooperation, or other). Size: (5 - faithfulness) / 4. Any OpenAI-compatible chat
endpoint (OpenAI, DeepSeek, Qwen, ...); the chat call is injected, so tests use a fake. Paid per call.
"""
import json
import os

import httpx

from src.drift.types import KINDS, Drift

MODEL = 'gpt-6-luna'   # the lowest-cost OpenAI model; any chat model works (model=...)
PROMPT = """You compare a source passage with its rendering (a translation, quotation or paraphrase in another
language or the same one) and judge how faithfully the rendering carries the source's meaning.

Source ({source_lang}):
{source}

Rendering ({rendering_lang}):
{rendering}

Answer with a JSON object:
{{"faithfulness": 1-5 (5: same meaning; 4: minor differences; 3: noticeable change; 2: substantially different;
  1: unrelated or opposite),
 "kind": one of {kinds} ("narrower": the rendering says more than the source, "broader": it says less,
  "shifted": neither, "contradicted": they conflict),
 "changes": a short description of what changed in meaning, "" if nothing,
 "direction": the direction of the change if it has one (e.g. "towards risk", "towards opportunity",
  "towards competition", "towards cooperation", or your own words), "" if none}}"""


def chat_completion(model=MODEL, base_url='https://api.openai.com/v1', key_env='OPENAI_API_KEY', timeout=120):
    """messages -> the reply's text, from an OpenAI-compatible chat endpoint (JSON output; temperature 0 where the
    model accepts it: some, like gpt-6-luna, only take their default, and the call is retried without it)."""
    key = os.environ[key_env]
    settings = {'temperature': 0}

    def chat(messages):
        while True:
            r = httpx.post(f'{base_url.rstrip("/")}/chat/completions', headers={'Authorization': f'Bearer {key}'},
                           json={'model': model, 'messages': messages, 'response_format': {'type': 'json_object'},
                                 **settings}, timeout=timeout)
            if r.status_code == 400 and settings and 'temperature' in r.text:
                settings.clear()       # this model doesn't take a temperature: drop it, from now on
                continue
            r.raise_for_status()
            return r.json()['choices'][0]['message']['content']
    return chat


class LLMDrift:
    def __init__(self, chat=None, model=MODEL, source_lang='en', rendering_lang='zh'):
        self.chat = chat or chat_completion(model)
        self.name = f'llm:{model}'
        self.langs = {'source_lang': source_lang, 'rendering_lang': rendering_lang}

    def score(self, source, rendering):
        prompt = PROMPT.format(source=source, rendering=rendering, kinds=', '.join(KINDS), **self.langs)
        reply = self.chat([{'role': 'user', 'content': prompt}])
        rating = json.loads(reply)
        faithfulness = min(5, max(1, int(rating['faithfulness'])))
        kind = rating.get('kind') if rating.get('kind') in KINDS else None
        return Drift(round((5 - faithfulness) / 4, 3), kind, self.name,
                     {'faithfulness': faithfulness, 'changes': rating.get('changes', ''),
                      'direction': rating.get('direction', '')})
