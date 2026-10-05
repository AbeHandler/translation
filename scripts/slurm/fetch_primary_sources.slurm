#!/bin/bash
# A worker of scripts/fetch_primary_sources.py: the raw text of the primary sources -> data/interim/primary/.
# Submit many (scripts/fetch_primary_sources.sh).
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/fetch_primary_sources.slurm
#   sbatch --export=MIN_OUTLETS=10 scripts/slurm/fetch_primary_sources.slurm

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

python -m scripts.fetch_primary_sources -min-outlets "${MIN_OUTLETS:-0}" -max-files "$MAX_FILES"
