#!/bin/bash
# One step of main/step3/crossings.py (STEP=embed_zh|screenshots|candidates|table|fit|one). embed_zh and candidates
# are workers: submit many. main/step3/go_step3.sh runs them all in order. STEP=one runs a single seed (SEED=its URL
# or seed_id) end to end -> data/interim/step3/one_<seed_id>.tsv, once embed_zh has been run.
#
# Usage (from the repo root; normally via main/step3/go_step3.sh):
#   sbatch --export=STEP=fit main/step3/crossings.slurm
#   sbatch --export=STEP=one,SEED=https://www.anthropic.com/news/statement-department-of-war main/step3/crossings.slurm

#SBATCH --partition=acpu
#SBATCH --time=12:00:00
#SBATCH --job-name=crossings
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${STEP:-}" ]; then
    echo "ERROR: STEP (embed_zh|screenshots|candidates|table|fit|one) is required"
    exit 1
fi

module load anaconda
conda activate translation

export HF_HOME=$TMP/huggingface               # LaBSE, downloaded once to the shared cache
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}

python -m main.step3.crossings -step "$STEP" -max-files "$MAX_FILES" ${SEED:+-seed "$SEED"}
