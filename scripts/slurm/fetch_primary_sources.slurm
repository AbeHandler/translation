#!/bin/bash
# A worker of scripts/fetch_primary_sources.py: the raw text of the URLs on data/interim/primary/todo.tsv
# -> data/interim/primary/<sha1>.json.
# Submit many (scripts/fetch_primary_sources.sh).
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/fetch_primary_sources.slurm

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=fetch_primary_sources
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=4G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

python -m scripts.fetch_primary_sources -max-files "$MAX_FILES"
