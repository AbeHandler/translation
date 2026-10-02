#!/bin/bash
# Build model1's feature matrix from the crawls (scripts/build_transmission_pairs.py: the linked English -> Chinese
# pairs, English articles from cc_html, Chinese documents from zh_docs), then fit model1 (scripts/fit_model1.py).
#   data/processed/news_en_zh_links_clean.jsonl + news_en_zh_sources.jsonl + data/interim/cc_html + zh_docs.jsonl
#   -> data/processed/transmission_pairs.csv, transmission_pairs.r.csv
# Run after clean_en_zh_links.slurm (the source cache says which WARC each English article is in) and the zh_docs
# fetch (bash scripts/go_zh_docs.sh).
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/build_transmission_pairs.slurm

#SBATCH --partition=acpu
#SBATCH --time=08:00:00
#SBATCH --job-name=build_transmission_pairs
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=32G
#SBATCH --cpus-per-task=8
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}
export HF_HOME=$TMP/huggingface  # LaBSE, shared cache

python -m scripts.build_transmission_pairs
python -m scripts.fit_model1
