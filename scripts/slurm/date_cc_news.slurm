#!/bin/bash
# One worker of scripts/date_cc_news.py: publication dates of the embedded English CC-NEWS articles, one file per
# WARC (data/interim/cc_news_pubdates/). scripts/date_cc_news.sh submits N of these.
#
# Usage (from the repo root; normally via scripts/date_cc_news.sh):
#   sbatch --export=NONE scripts/slurm/date_cc_news.slurm
#   optional: MAX_FILES=1 (test)

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=date_cc_news
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

# MAX_FILES may be empty; the script treats empty as "no limit".
python -m scripts.date_cc_news -max-files "$MAX_FILES"
