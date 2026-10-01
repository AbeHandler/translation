#!/bin/bash
# Clean the collected English -> Chinese CC-NEWS links (scripts/clean_en_zh_links.py): drop failed fetches and
# Chinese sources, add story_id / story_size / is_press_release.
#   data/processed/news_en_zh_links.jsonl -> data/processed/news_en_zh_links_clean.jsonl
# Run the collect first (python -m scripts.collect_queue, or COLLECT_ONLY=1 bash scripts/process_queue.sh news).
# The first run reads every cc_links file for source titles (~90 min for 21.7k files); later runs look up only
# sources not in the title cache (but that still means one pass over the links files).
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/clean_en_zh_links.slurm

#SBATCH --partition=acpu
#SBATCH --time=08:00:00
#SBATCH --job-name=clean_en_zh_links
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=4G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

python -m scripts.clean_en_zh_links
