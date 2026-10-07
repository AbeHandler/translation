#!/bin/bash
# One step of main/step2/seed_citations.py: STEP=citations (a worker; submit many) or STEP=salience (one job, after
# them). main/step2/go_step2.sh runs both.
#
# Usage (from the repo root; normally via main/step2/go_step2.sh):
#   sbatch --export=STEP=salience main/step2/seed_citations.slurm

#SBATCH --partition=acpu
#SBATCH --time=12:00:00
#SBATCH --job-name=seed_citations
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${STEP:-}" ]; then
    echo "ERROR: STEP (citations|salience) is required"
    exit 1
fi

module load anaconda
conda activate translation

python -m main.step2.seed_citations -step "$STEP" -max-files "$MAX_FILES"
