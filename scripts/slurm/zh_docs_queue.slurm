#!/bin/bash
# Queue the linked Chinese pages for fetching as documents (scripts/zh_docs_queue.py): the cleaned en->zh link
# files -> $TMP/zh_docs_queue (TMP from ~/.myrc). Quick: it only reads the cleaned link files. Then fetch them:
#   bash scripts/process_queue.sh zh_docs
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/zh_docs_queue.slurm

#SBATCH --partition=acpu
#SBATCH --time=01:00:00
#SBATCH --job-name=zh_docs_queue
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=4G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set (in ~/.myrc); the queue goes in \$TMP/zh_docs_queue"
    exit 1
fi

module load anaconda
conda activate translation

python -m scripts.zh_docs_queue
