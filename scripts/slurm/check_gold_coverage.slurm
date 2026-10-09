#!/bin/bash
# Where a gold list of Chinese articles about one event is lost before the media storms (scripts/check_gold_coverage.py)
#
# Usage (from the repo root):
#   sbatch --export=GOLD=config/gold/chinese_coverage_hf_openai_anthropic.csv scripts/slurm/check_gold_coverage.slurm

#SBATCH --partition=acpu
#SBATCH --time=04:00:00
#SBATCH --job-name=check_gold_coverage
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc
module load anaconda
conda activate translation

python -m scripts.check_gold_coverage -gold "${GOLD:-config/gold/chinese_coverage_hf_openai_anthropic.csv}" ${ALL:+-all}
