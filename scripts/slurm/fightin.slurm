#!/bin/bash
# One Fightin' Words experiment (scripts/fightin.py): a selection (config/fightin_selections.tsv) at a sample size,
# English vs Chinese AI coverage. Samples up to N AI documents per language in the selection (reused if already
# sampled), counts phrases of 2-3 words, embeds them (reused if unchanged), compares and plots.
# Outputs: results/fightin/<SELECTION>_<N in thousands>k/. Normally submitted by scripts/go_fightin.sh.
#
# Usage (from the repo root):
#   sbatch --export=SELECTION=openai,N=5000 scripts/slurm/fightin.slurm
#   sbatch --export=SELECTION=all,N=20000,NGRAMS=1 scripts/slurm/fightin.slurm   # words, same sample
#   sbatch --export=SELECTION=openai,N=5000,STEP=flush scripts/slurm/fightin.slurm  # delete its outputs

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=fightin
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=48G
#SBATCH --cpus-per-task=4
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc
module load anaconda
conda activate translation

export HF_HOME=$TMP/huggingface               # LaBSE, downloaded once to the shared cache
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}

echo "fightin: SELECTION=${SELECTION:-all} N=${N:-20000} NGRAMS=${NGRAMS:-2-3}"
python -m scripts.fightin -step "${STEP:-all}" -selection "${SELECTION:-all}" -n "${N:-20000}" -ngrams "${NGRAMS:-2-3}"
