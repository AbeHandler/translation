#!/bin/bash
# One job of scripts/cc_full.py (STEP=list|filter|all|links|queue|cleanup): the regular Common Crawl's English pages saying "AI",
# in $TMP/cc_full/ (TMP from ~/.myrc). scripts/go_cc_full.sh submits the list job and the filter workers.
#
# Usage (from the repo root; normally via scripts/go_cc_full.sh):
#   sbatch --job-name=cc_full_filter --export=STEP=filter scripts/slurm/cc_full.slurm
#   sbatch --job-name=cc_full_cleanup --export=STEP=cleanup scripts/slurm/cc_full.slurm   # delete AI WARCs with links
#   optional: MAX_WARCS=1 (test), SINCE_YEAR=2023

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=cc_full
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=4G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${STEP:-}" ] || [ -z "${TMP:-}" ]; then
    echo "ERROR: STEP (list|filter|all|links|queue|cleanup) is required, and TMP (from ~/.myrc)"
    exit 1
fi

module load anaconda
conda activate translation

python -m scripts.cc_full -step "$STEP" -since-year "${SINCE_YEAR:-2023}" -max-warcs "$MAX_WARCS"
