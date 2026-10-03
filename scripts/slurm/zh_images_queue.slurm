#!/bin/bash
# Queue the linked Chinese pages for fetching as documents (scripts/zh_images_queue.py): the cleaned en->zh link
# -> $TMP/zh_images_queue (TMP from ~/.myrc). Quick. Then screen them:
#   bash scripts/process_queue.sh zh_images
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/zh_images_queue.slurm

#SBATCH --partition=acpu
#SBATCH --time=01:00:00
#SBATCH --job-name=zh_images_queue
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
    echo "ERROR: \$TMP is not set (in ~/.myrc); the queue goes in \$TMP/zh_images_queue"
    exit 1
fi

module load anaconda
conda activate translation

python -m scripts.zh_images_queue
