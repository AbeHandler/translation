#!/bin/bash
# Add to $TMP/cc_news_queue (only links not queued or done yet): the external links of CC-NEWS articles saying
# "AI" (scripts/cc_news_queue.py; needs cc_html and cc_links, not NER), for scripts/process_queue.sh news.
# scripts/go_zh_en.sh submits it after its links workers.
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/cc_news_queue.slurm      # TMP comes from ~/.myrc
#   sbatch --export=START_DATE=20260223,END_DATE=20260302,MIN_AI_MENTIONS=2 scripts/slurm/cc_news_queue.slurm
#   sbatch --export=FRESH=1,MIN_AI_MENTIONS=3 scripts/slurm/cc_news_queue.slurm   # delete the queue first, start over

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=cc_news_queue
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=32G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set (in ~/.myrc); the queue goes in \$TMP/cc_news_queue"
    exit 1
fi

module load anaconda
conda activate translation

python -m scripts.cc_news_queue -start-date "$START_DATE" -end-date "$END_DATE" -min-ai-mentions "${MIN_AI_MENTIONS:-1}" \
    ${FRESH:+-fresh}
