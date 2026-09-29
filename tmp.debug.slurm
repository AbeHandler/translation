#!/bin/bash
# Why so few English->Chinese links? Looks at data/processed/news_link_languages.jsonl (the collected link-language
# results) and writes tmp_debug_report.txt:
#   overall counts (rows, languages, errors, citing articles, status codes)
#   Chinese-looking hosts (by address) among rows NOT labelled zh: are failures hiding Chinese links?
#   the upper bound: every link to a Chinese-looking address, whatever the label
#   the zh links by the citing article's language (from cc_ner): how many are really English -> Chinese
# Only reads. Python rather than jq.
#
# Usage (from the repo root):
#   sbatch --export=NONE tmp.debug.slurm

#SBATCH --partition=acpu
#SBATCH --time=01:00:00
#SBATCH --job-name=tmp_debug
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

python - <<'PY'
import collections, glob, json, re
import pyarrow.parquet as pq

F = 'data/processed/news_link_languages.jsonl'
CHINESE_HOST = re.compile(r'\.cn$|weixin|weibo|baidu|(^|\.)qq\.com|163\.com|sina\.|sohu|xinhua|news\.cn|people\.com|'
                          r'chinadaily|36kr|zhihu|bilibili|douyin|toutiao|caixin|thepaper|ifeng|huxiu|jiemian|yicai|'
                          r'youku|cctv|cgtn|globaltimes|huanqiu|chinanews|gov\.cn|jd\.com|taobao|alibaba|tencent|'
                          r'bytedance|deepseek|moonshot|kimi|zhipu|minimax|scmp|caixinglobal', re.I)
rows = [json.loads(line) for line in open(F, encoding='utf-8')]
out = []
def say(*lines):
    out.extend(lines)

label = lambda r: r.get('language') or 'ERROR'
say(f'{len(rows)} links from {len({r["srcpage"] for r in rows})} AI articles to {len({r.get("host") for r in rows})} hosts', '')
say('== languages of the linked pages')
say(*[f'  {n:8d}  {v}' for v, n in collections.Counter(map(label, rows)).most_common(15)], '')
say('== label source')
say(*[f'  {n:8d}  {v}' for v, n in collections.Counter(r.get('label_source', 'ERROR') for r in rows).most_common()], '')
say('== error types')
say(*[f'  {n:8d}  {v}' for v, n in collections.Counter(r['error'].split(':')[0] for r in rows if 'error' in r).most_common(10)], '')
say('== HTTP status of fetched pages')
say(*[f'  {n:8d}  {v}' for v, n in collections.Counter(r.get('status') for r in rows if 'status' in r).most_common(10)], '')

chinese = [r for r in rows if CHINESE_HOST.search(r.get('host') or '')]
say(f'== links to Chinese-looking hosts (by address): {len(chinese)} (upper bound; incl. scmp etc., English sites)')
say(*[f'  {n:8d}  {v}' for v, n in collections.Counter(map(label, chinese)).most_common()], '')
say('== Chinese-looking hosts NOT labelled zh: host, label, status / error')
hidden = collections.Counter((r.get('host'), label(r), r.get('status') or r.get('error', '')[:40])
                             for r in chinese if r.get('language') != 'zh')
say(*[f'  {n:6d}  {h}  {l}  {s}' for (h, l, s), n in hidden.most_common(40)], '')

# the citing article's language, from cc_ner
zh = [r for r in rows if r.get('language') == 'zh']
wanted = {r['srcpage'] for r in zh}
src_lang = {}
for path in glob.glob('data/interim/cc_ner/*.parquet'):
    t = pq.read_table(path, columns=['url', 'language']).to_pydict()
    for url, lang in zip(t['url'], t['language']):
        if url in wanted:
            src_lang[url] = lang
say(f'== the {len(zh)} zh links by citing article language (en -> zh is what we want)')
say(*[f'  {n:8d}  {v}' for v, n in collections.Counter(src_lang.get(r['srcpage'], '?') for r in zh).most_common()], '')
say('== the zh links')
for r in zh:
    say(f'  [{src_lang.get(r["srcpage"], "?")}->zh] {r["srcpage"][:90]}', f'      -> {r["url"][:100]}  {r.get("title", "")[:60]}')

with open('tmp_debug_report.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out) + '\n')
print('\n'.join(out[:40]))
print('-> tmp_debug_report.txt')
PY
