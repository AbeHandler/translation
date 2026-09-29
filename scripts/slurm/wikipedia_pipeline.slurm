#!/bin/bash
# One step of scripts/wikipedia_pipeline.py for one language (WIKI_LANG; not LANG, the shell's locale).
# scripts/go_wikipedia.sh submits them in order; pages runs as many workers.
#
# Usage (from the repo root; normally via scripts/go_wikipedia.sh):
#   sbatch --job-name=wikipedia_pages --export=WIKI_LANG=zh,STEP=pages,TMP=$TMP scripts/slurm/wikipedia_pipeline.slurm
#   optional: MAX_CHUNKS=1 (test)

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=wikipedia_pipeline
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

if [ -z "${WIKI_LANG:-}" ] || [ -z "${STEP:-}" ] || [ -z "${TMP:-}" ]; then
    echo "ERROR: WIKI_LANG (e.g. zh), STEP (download|pages|filter|queue) and TMP are required"
    exit 1
fi

module load anaconda
conda activate translation

python -m scripts.wikipedia_pipeline -lang "$WIKI_LANG" -step "$STEP" -max-chunks "$MAX_CHUNKS"
