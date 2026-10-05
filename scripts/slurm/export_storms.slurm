#!/bin/bash
# Export the largest media storms for reading (scripts/export_storms.py) -> data/processed/storms_review.json.
# Run after the storms step of scripts/go_media_storms.sh.
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/export_storms.slurm
#   sbatch --export=TOP=1000 scripts/slurm/export_storms.slurm
#   sbatch --export=CORPUS=zh scripts/slurm/export_storms.slurm   # the Chinese storms

#SBATCH --partition=acpu
#SBATCH --time=04:00:00
#SBATCH --job-name=export_storms
#SBATCH --output=logs/scripts/slurm/%x_%j.out
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

python -m scripts.export_storms -top "${TOP:-500}" -corpus "${CORPUS:-en}"
