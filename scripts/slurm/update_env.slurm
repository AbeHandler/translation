#!/bin/bash
# Create the translation conda env (Python only, so conda has almost nothing to solve) and
# pip install config/requirements.txt into it. Fast to rerun. Submitted by scripts/go.sh.
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/update_env.slurm   # NONE: don't inherit the login node's modules

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
PYTHON_VERSION=3.11.14  # matches the local env the code was tested with

module load anaconda
if ! conda env list | grep -q "^${ENV_NAME} "; then
    conda create -y -n "$ENV_NAME" "python=$PYTHON_VERSION" pip
fi
conda activate "$ENV_NAME"
pip install -r config/requirements.txt
python -c "import newsplease, newspaper, htmldate, warcio, readability, lxml, tqdm, scrapy, torch, sentence_transformers, annoy; print('env ok')"
