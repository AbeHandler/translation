#!/bin/bash
# Rebuild data/processed/gazetteer_stories.jsonl: every CC-NEWS story naming an entry of config/gazetteer.yaml
# among its named entities (scripts/filter_by_gazetteer.py). scripts/go.sh submits it after the ner workers.
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/filter_by_gazetteer.slurm
#   sbatch --export=START_DATE=20260223,END_DATE=20260302 scripts/slurm/filter_by_gazetteer.slurm   # one range
#   optional: MAX_N=100 (the test files)

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=filter_by_gazetteer
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

python -m scripts.filter_by_gazetteer \
    ${START_DATE:+-start-date "$START_DATE"} \
    ${END_DATE:+-end-date "$END_DATE"} \
    ${MAX_N:+-max-n "$MAX_N"}
