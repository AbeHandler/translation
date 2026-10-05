#!/bin/bash
# One step of scripts/media_storms.py (STEP=by_day|edges|cluster|storms|seeds; CORPUS=en|zh, default en).
# by_day and edges are workers: submit many. scripts/go_media_storms.sh runs them all in order.
#
# Usage (from the repo root; normally via scripts/go_media_storms.sh):
#   sbatch --export=STEP=edges scripts/slurm/media_storms.slurm
#   optional: CORPUS=zh, MAX_FILES=1 (test), REDO_EDGES=1 (edges: recompute days already done)

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=media_storms
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=32G
#SBATCH --cpus-per-task=8
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${STEP:-}" ]; then
    echo "ERROR: STEP (by_day|edges|cluster|storms) is required"
    exit 1
fi

module load anaconda
conda activate translation

export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}   # the edges' matrix products

python -m scripts.media_storms -corpus "${CORPUS:-en}" -step "$STEP" -max-files "$MAX_FILES" ${REDO_EDGES:+-redo-edges}
