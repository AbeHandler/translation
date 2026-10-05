#!/bin/bash
# One step of scripts/primary_sources.py (STEP=links|sources|flush). links is a worker: submit many.
# scripts/go_primary_sources.sh runs them in order.
#
# Usage (from the repo root; normally via scripts/go_primary_sources.sh):
#   sbatch --export=STEP=sources scripts/slurm/primary_sources.slurm

#SBATCH --partition=acpu
#SBATCH --time=12:00:00
#SBATCH --job-name=primary_sources
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${STEP:-}" ]; then
    echo "ERROR: STEP (links|sources|flush) is required"
    exit 1
fi

module load anaconda
conda activate translation

python -m scripts.primary_sources -step "$STEP" -max-files "$MAX_FILES"
