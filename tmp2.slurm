#!/bin/bash
# Try the company filters on the gazetteer quotes (data/processed/gazetteer_quotes.jsonl, or its .part while
# extract_quotes is still running). Writes:
#   tmp2_report.txt       counts per filter and per company, and a few random examples of each
#   tmp2_cn_quotes.jsonl  quotes (>= 4 words) whose paragraph, quote or speaker names a Chinese AI company
# Python rather than jq, so it doesn't depend on jq being installed. Only reads.
#
# Usage (from the repo root):
#   sbatch --export=NONE tmp2.slurm

#SBATCH --partition=acpu
#SBATCH --time=01:00:00
#SBATCH --job-name=tmp2
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=4G
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
import collections, json, os, random, re

random.seed(0)
path = 'data/processed/gazetteer_quotes.jsonl'
if not os.path.exists(path):
    path += '.part'
CN = ['DeepSeek', 'Moonshot AI', 'MiniMax', 'Zhipu AI', 'Baichuan', 'StepFun', '01.AI', 'Qwen', 'Doubao']
CN_TEXT = re.compile(r'DeepSeek|Moonshot|Kimi|MiniMax|Zhipu|Baichuan|StepFun|01\.AI|Qwen|Doubao', re.I)

rows = []
with open(path, encoding='utf-8') as f:
    for line in f:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:  # the last line of a .part still being written
            pass

filters = {
    'any company named in the paragraph': lambda r: len(r['paragraph_canonicals']) > 0,
    'a Chinese AI company named in the paragraph': lambda r: any(c in CN for c in r['paragraph_canonicals']),
    'a Chinese AI company named in the quote or speaker': lambda r: bool(CN_TEXT.search(r['quote'] + ' ' + (r['speaker'] or ''))),
}
out = [f'{len(rows)} quotes in {path}', '']
for name, keep in filters.items():
    kept = [r for r in rows if keep(r) and r['n_words'] >= 4]
    out.append(f'== {name} (>= 4 words): {len(kept)}')
    for r in random.sample(kept, min(5, len(kept))):
        out.append(f"  - {r['speaker']!r} ({r['quote_type']}) {r['paragraph_canonicals']}: {r['quote'][:200]!r}")
        out.append(f"    {r['url']}")
    out.append('')
out.append('== quotes per company named in the paragraph')
counts = collections.Counter(c for r in rows for c in r['paragraph_canonicals'])
out += [f'  {n:6d}  {c}' for c, n in counts.most_common()]
out.append('')
out.append('== most quoted speakers, Chinese AI company in the paragraph')
speakers = collections.Counter(r['speaker'] or 'NONE' for r in rows if filters['a Chinese AI company named in the paragraph'](r))
out += [f'  {n:6d}  {s}' for s, n in speakers.most_common(30)]

with open('tmp2_report.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out) + '\n')
with open('tmp2_cn_quotes.jsonl', 'w', encoding='utf-8') as f:
    for r in rows:
        if r['n_words'] >= 4 and (filters['a Chinese AI company named in the paragraph'](r)
                                  or filters['a Chinese AI company named in the quote or speaker'](r)):
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
print('\n'.join(out[:12]))
print('-> tmp2_report.txt, tmp2_cn_quotes.jsonl')
PY
