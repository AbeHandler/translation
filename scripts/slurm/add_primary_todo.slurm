#!/bin/bash
# Add URLs to the primary-source store's to-do list (scripts/add_primary_todo.py): all the primary sources, English
# and Chinese (data/processed/primary_sources.tsv and primary_sources_zh.tsv, whichever exist; linked by
# MIN_OUTLETS+ outlets), or, if TSV is given, that TSV's URL column instead.
#
# Usage (from the repo root; normally via scripts/fetch_primary_sources.sh):
#   sbatch --export=NONE scripts/slurm/add_primary_todo.slurm
#   sbatch --export=MIN_OUTLETS=5 scripts/slurm/add_primary_todo.slurm
#   sbatch --export=TSV=data/processed/cac_links.tsv,COLUMN=cac_url scripts/slurm/add_primary_todo.slurm

#SBATCH --partition=acpu
#SBATCH --time=01:00:00
#SBATCH --job-name=add_primary_todo
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

if [ -n "${TSV:-}" ]; then
    python -m scripts.add_primary_todo -tsv "$TSV" -column "${COLUMN:-url}"
else
    for tsv in data/processed/primary_sources.tsv data/processed/primary_sources_zh.tsv; do
        if [ -f "$tsv" ]; then
            python -m scripts.add_primary_todo -primary-sources "$tsv" -min-outlets "${MIN_OUTLETS:-0}"
        else
            echo "skipping $tsv: not there"
        fi
    done
fi
