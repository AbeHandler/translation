#!/bin/bash
# Create or update the translation conda env from config/translation.yml. Submitted by scripts/go.sh.
#
# Usage (from the repo root):
#   sbatch scripts/slurm/update_env.slurm

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=update_env
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

ENV_NAME=translation
ENV_FILE=config/translation.yml

module load anaconda
if conda env list | grep -q "^${ENV_NAME} "; then
    conda env update -n "$ENV_NAME" -f "$ENV_FILE"  # no --prune: keep packages not in the yml
else
    conda env create -f "$ENV_FILE"
fi
