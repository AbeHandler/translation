#!/bin/bash
# Compile the primary-source store into data/processed/primary.pq (scripts/compile_primary_sources.py).
# scripts/fetch_primary_sources.sh runs it after its workers.
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/compile_primary_sources.slurm

#SBATCH --partition=acpu
#SBATCH --time=02:00:00
#SBATCH --job-name=compile_primary_sources
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

python -m scripts.compile_primary_sources
