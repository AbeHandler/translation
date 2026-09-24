"""
Translation engines. Each backend splits a call in two, so the raw response can be stored before anything
that might fail on it:
    request(text, src, tgt, context_mode, temperature) -> raw response (a JSON-able dict)
    parse(raw) -> the translation
    prompt(text, src, tgt, context_mode) -> the prompt sent ('' for NMT); for an LLM it is part of the method
NMT backends (is_llm False) only translate isolated sentences: they can't be asked to translate just the
marked sentence of a window.

ENGINES maps an engine name to a function building its backend; build_engines() raises if a backend's
API key (env var) is missing, rather than quietly running without it.
"""
import hashlib
import os
import random
import string

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


class EngineHTTPError(Exception):
    """An engine answered with an HTTP error. Carries the response body, which says what was wrong
    (e.g. xAI: 'Incorrect API key provided'), so it ends up in the stored error."""

    def __init__(self, response):
        self.status_code = response.status_code
        super().__init__(f'HTTP {response.status_code} from {response.url}: {response.text[:500]}')


def checked_json(response):
    if response.is_error:
        raise EngineHTTPError(response)
    return response.json()


def is_transient(exc):
    """Worth retrying: rate limits, server errors, timeouts and dropped connections. Not other 4xx errors
    (bad key, bad request): they fail the same way every time."""
    if isinstance(exc, EngineHTTPError):
        return exc.status_code == 429 or exc.status_code >= 500
    return isinstance(exc, httpx.TransportError)


# Transient failures get 4 tries; reraise so the store sees the real error.
retry_calls = retry(retry=retry_if_exception(is_transient), stop=stop_after_attempt(4),
                    wait=wait_exponential(min=2, max=30), reraise=True)


class Backend:
    name = 'base'
    model = ''
    is_llm = False

    def request(self, text, src, tgt, context_mode='isolated', temperature=0.0):
        raise NotImplementedError

    def parse(self, raw):
        raise NotImplementedError

    def prompt(self, text, src, tgt, context_mode='isolated'):
        return ''


class GoogleV2(Backend):
    """Classic NMT. $20/M chars, first 500k/month free, permanently."""
    name, model = 'google', 'nmt-v2'

    def __init__(self):
        self.key = os.environ['GOOGLE_TRANSLATE_API_KEY']

    @retry_calls
    def request(self, text, src, tgt, context_mode='isolated', temperature=0.0):
        r = httpx.post('https://translation.googleapis.com/language/translate/v2', params={'key': self.key},
                       json={'q': text, 'source': src, 'target': tgt, 'format': 'text'}, timeout=60)
        return checked_json(r)

    def parse(self, raw):
        return raw['data']['translations'][0]['translatedText']


class GoogleV3LLM(Backend):
    """v3 Translation LLM. Same vendor as GoogleV2 but a different model class: the cleanest NMT-vs-LLM
    comparison available (training data and vendor roughly constant, model class varied). Its prompt is
    Google's, not ours, so it runs as NMT does: isolated sentences, one sample.

    Needs GOOGLE_CLOUD_PROJECT, application-default credentials and `pip install google-auth`.
    Not covered by the 500k free tier: $10/M in + $10/M out.
    """
    name, model = 'google', 'translation-llm'

    def __init__(self):
        import google.auth
        from google.auth.transport.requests import Request
        self.project = os.environ['GOOGLE_CLOUD_PROJECT']
        self.location = os.environ.get('GOOGLE_CLOUD_LOCATION', 'us-central1')
        self.creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        self._auth_request = Request

    def _token(self):
        if not self.creds.valid:
            self.creds.refresh(self._auth_request())
        return self.creds.token

    @retry_calls
    def request(self, text, src, tgt, context_mode='isolated', temperature=0.0):
        parent = f'projects/{self.project}/locations/{self.location}'
        r = httpx.post(f'https://translate.googleapis.com/v3/{parent}:translateText',
                       headers={'Authorization': f'Bearer {self._token()}'},
                       json={'contents': [text], 'sourceLanguageCode': src, 'targetLanguageCode': tgt,
                             'model': f'{parent}/models/general/translation-llm'},
                       timeout=90)
        return checked_json(r)

    def parse(self, raw):
        return raw['translations'][0]['translatedText']


class Baidu(Backend):
    """fanyi-api.baidu.com general translation. The standard tier needs no 实名认证 and gives 50k chars/month
    free, ample for a probe set. The advanced tier (1M/month) requires Chinese identity verification."""
    name, model = 'baidu', 'general-standard'
    LANGUAGES = {'en': 'en', 'zh': 'zh', 'zh-CN': 'zh', 'zh-Hans': 'zh', 'zh-cn': 'zh'}

    def __init__(self):
        self.appid = os.environ['BAIDU_APPID']
        self.key = os.environ['BAIDU_SECRET_KEY']

    @retry_calls
    def request(self, text, src, tgt, context_mode='isolated', temperature=0.0):
        salt = ''.join(random.choices(string.digits, k=10))
        sign = hashlib.md5((self.appid + text + salt + self.key).encode('utf-8')).hexdigest()
        r = httpx.post('https://fanyi-api.baidu.com/api/trans/vip/translate',
                       data={'q': text, 'from': self.LANGUAGES.get(src, src), 'to': self.LANGUAGES.get(tgt, tgt),
                             'appid': self.appid, 'salt': salt, 'sign': sign},
                       timeout=60)
        return checked_json(r)

    def parse(self, raw):
        if 'error_code' in raw:
            raise RuntimeError(f"baidu {raw['error_code']}: {raw.get('error_msg')}")
        return '\n'.join(line['dst'] for line in raw['trans_result'])  # one object per input line


class DeepL(Backend):
    name, model = 'deepl', 'v2'

    def __init__(self):
        self.key = os.environ['DEEPL_API_KEY']
        self.host = 'api-free.deepl.com' if self.key.endswith(':fx') else 'api.deepl.com'

    @retry_calls
    def request(self, text, src, tgt, context_mode='isolated', temperature=0.0):
        r = httpx.post(f'https://{self.host}/v2/translate',
                       headers={'Authorization': f'DeepL-Auth-Key {self.key}'},
                       json={'text': [text], 'source_lang': src.split('-')[0].upper(),
                             'target_lang': 'ZH' if tgt.lower().startswith('zh') else tgt.upper()},
                       timeout=60)
        return checked_json(r)

    def parse(self, raw):
        return raw['translations'][0]['text']


class OpenAICompatLLM(Backend):
    """Any OpenAI-shaped chat endpoint: OpenAI, DeepSeek, Qwen (DashScope compatible mode), Moonshot,
    Zhipu, xAI (Grok), or a local vLLM server."""
    is_llm = True
    PROMPTS = {
        'isolated': ('Translate the following {src_name} text into {tgt_name}. '
                     'Output only the translation, with no commentary.\n\n{text}'),
        'windowed': ('Below is a passage in {src_name}. Translate ONLY the sentence marked with <<< >>> into '
                     '{tgt_name}, using the surrounding text for context. Output only the translation of the '
                     'marked sentence, without the markers and without commentary.\n\n{text}'),
    }
    LANGUAGE_NAMES = {'en': 'English', 'zh': 'Chinese', 'zh-CN': 'Chinese', 'zh-Hans': 'Chinese'}

    def __init__(self, name, model, base_url, key_env):
        self.name = name
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.key = os.environ[key_env]

    def prompt(self, text, src, tgt, context_mode='isolated'):
        return self.PROMPTS[context_mode].format(src_name=self.LANGUAGE_NAMES.get(src, src),
                                                 tgt_name=self.LANGUAGE_NAMES.get(tgt, tgt), text=text)

    @retry_calls
    def request(self, text, src, tgt, context_mode='isolated', temperature=0.0):
        r = httpx.post(f'{self.base_url}/chat/completions',
                       headers={'Authorization': f'Bearer {self.key}'},
                       json={'model': self.model, 'temperature': temperature,
                             'messages': [{'role': 'user', 'content': self.prompt(text, src, tgt, context_mode)}]},
                       timeout=180)
        return checked_json(r)

    def parse(self, raw):
        return raw['choices'][0]['message']['content'].strip()


ENGINES = {
    'google_nmt': GoogleV2,
    'google_llm': GoogleV3LLM,
    'baidu': Baidu,
    'deepl': DeepL,
    'openai': lambda: OpenAICompatLLM('openai', 'gpt-4o', 'https://api.openai.com/v1', 'OPENAI_API_KEY'),
    'deepseek': lambda: OpenAICompatLLM('deepseek', 'deepseek-chat', 'https://api.deepseek.com/v1',
                                        'DEEPSEEK_API_KEY'),
    'qwen': lambda: OpenAICompatLLM('qwen', 'qwen-max', 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1',
                                    'DASHSCOPE_API_KEY'),
    'moonshot': lambda: OpenAICompatLLM('moonshot', 'moonshot-v1-8k', 'https://api.moonshot.cn/v1',
                                        'MOONSHOT_API_KEY'),
    'zhipu': lambda: OpenAICompatLLM('zhipu', 'glm-4-plus', 'https://open.bigmodel.cn/api/paas/v4', 'ZHIPU_API_KEY'),
    'grok': lambda: OpenAICompatLLM('grok', 'grok-4.6', 'https://api.x.ai/v1', 'XAI_API_KEY'),
}


def build_engines(names):
    """Backends for the named engines. Raises listing every engine whose API key (env var) is missing."""
    unknown = [name for name in names if name not in ENGINES]
    if unknown:
        raise ValueError(f'unknown engines {unknown}; choices: {", ".join(sorted(ENGINES))}')
    engines, missing = [], []
    for name in names:
        try:
            engines.append(ENGINES[name]())
        except KeyError as exc:
            missing.append(f'{name} needs {exc}')
    if missing:
        raise EnvironmentError('missing API keys (set them, or leave the engine out with -engines): '
                               + '; '.join(missing))
    return engines
