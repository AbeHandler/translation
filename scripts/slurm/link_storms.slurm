#!/bin/bash
# Link English and Chinese media storms about the same event (scripts/link_storms.py) from their exports
# (data/processed/storms_review.json, storms_review_zh.json: made by the storm pipelines' export step) ->
# data/processed/storm_links.tsv. main/step1/go_step1.sh runs it before build_seeds, which counts the links per seed.
#
# Usage (from the repo root):
#   sbatch scripts/slurm/link_storms.slurm

#SBATCH --partition=acpu
#SBATCH --time=02:00:00
#SBATCH --job-name=link_storms
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc
module load anaconda
conda activate translation

export HF_HOME=$TMP/huggingface               # LaBSE, downloaded once to the shared cache
export TOKENIZERS_PARALLELISM=false
python -m scripts.link_storms
