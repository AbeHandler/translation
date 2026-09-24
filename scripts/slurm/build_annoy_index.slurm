#!/bin/bash
# Rebuild the Annoy index over all site crawl embeddings (scripts/build_annoy_index.py), replacing the old one.
# scripts/site_crawls_go.sh submits this after the embedding workers.
#
# Usage (from the repo root; the env must have annoy, so run update_env first if it hasn't since):
#   sbatch --export=NONE scripts/slurm/build_annoy_index.slurm   # NONE: see scripts/go.sh

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=build_annoy_index
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=64G
#SBATCH --cpus-per-task=16
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

python -m scripts.build_annoy_index
