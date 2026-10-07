#!/bin/bash
# Step 1: build the seed table (main/step1/build_seeds.py) -> data/processed/seeds.tsv, from the English and Chinese
# link tables (scripts/primary_sources.py -step links) and config/seeds_extra.tsv.
#
# Usage (from the repo root):
#   sbatch main/step1/build_seeds.slurm
#   sbatch --export=MIN_OUTLETS=10 main/step1/build_seeds.slurm

#SBATCH --partition=acpu
#SBATCH --time=04:00:00
#SBATCH --job-name=build_seeds
#SBATCH --output=logs/scripts/slurm/%x_%j.out   # SLURM won't create a missing log folder
#SBATCH --mem=64G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

python -m main.step1.build_seeds -min-outlets "${MIN_OUTLETS:-5}"
