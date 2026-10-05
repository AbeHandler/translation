#!/bin/bash
# The primary-source documents behind the English media storms
# (scripts/export_seed_documents.py) -> data/processed/seed_documents.tsv. After the seeds step.
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/export_seed_documents.slurm

#SBATCH --partition=acpu
#SBATCH --time=04:00:00
#SBATCH --job-name=export_seed_documents
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

python -m scripts.export_seed_documents
