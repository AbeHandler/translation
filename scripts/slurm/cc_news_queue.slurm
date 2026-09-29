#!/bin/bash
# Rebuild $TMP/cc_news_queue: the external links of CC-NEWS articles about AI (scripts/cc_news_queue.py), for
# scripts/process_queue.sh.
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/cc_news_queue.slurm      # TMP comes from ~/.myrc
#   sbatch --export=START_DATE=20260223,END_DATE=20260302,MIN_AI_MENTIONS=2 scripts/slurm/cc_news_queue.slurm

#SBATCH --partition=acpu
#SBATCH --time=04:00:00
#SBATCH --job-name=cc_news_queue
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
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

python -m scripts.cc_news_queue -start-date "$START_DATE" -end-date "$END_DATE" -min-ai-mentions "${MIN_AI_MENTIONS:-1}"
