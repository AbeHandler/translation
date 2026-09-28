#!/bin/bash
# Rebuild data/processed/gazetteer_quotes.jsonl: the direct quotes in the gazetteer stories
# (scripts/extract_quotes.py). scripts/go_zh_en.sh submits it after filter_by_gazetteer.
#
# Usage (from the repo root; needs the model from scripts/slurm/train_quote_extractor.slurm):
#   sbatch --export=NONE scripts/slurm/extract_quotes.slurm
#   optional: MAX_N=100 (the test files)

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=extract_quotes
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
#SBATCH --cpus-per-task=8
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

python -m scripts.extract_quotes ${MAX_N:+-max-n "$MAX_N"}
