#!/bin/bash
# Fightin' Words between English (CC-NEWS) and Chinese (site crawls) AI coverage, on concepts shared via LaBSE
# (scripts/fightin.py). STEP=all (the default) runs sample, words, embed, fight, plot in order: sample is reused if
# docs.parquet exists, embed if index.npz already has the units; the rest always rerun. So after any change, just
# sbatch this again. Outputs: results/fightin/<EXPERIMENT>/.
#
# Usage (from the repo root):
#   sbatch scripts/slurm/fightin.slurm
#   sbatch --export=NGRAMS=2-3 scripts/slurm/fightin.slurm          # phrases of 2-3 words, on the same sample
#   sbatch --export=SELECTION=openai,PATTERN=OpenAI scripts/slurm/fightin.slurm         # only documents naming OpenAI
#   sbatch --export=SELECTION=anthropic,PATTERN='Anthropic|Claude' scripts/slurm/fightin.slurm
#   sbatch --export=SELECTION=h1_2025,FROM=2025-01-01,TO=2025-06-30 scripts/slurm/fightin.slurm
#   sbatch --export=SELECTION=mine,IDS=path/to/ids.txt scripts/slurm/fightin.slurm     # any list of document ids
#   sbatch --export=EXPERIMENT=en_vs_zh_ai_20k,N=20000,PER_FILE=100 scripts/slurm/fightin.slurm   # a bigger sample
#   sbatch --export=STEP=flush,EXPERIMENT=en_vs_zh_ai scripts/slurm/fightin.slurm                # delete outputs

#SBATCH --partition=acpu
#SBATCH --time=12:00:00
#SBATCH --job-name=fightin
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=24G
#SBATCH --cpus-per-task=4
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc
module load anaconda
conda activate translation

export HF_HOME=$TMP/huggingface               # LaBSE, downloaded once to the shared cache
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}

python -m scripts.fightin -step "${STEP:-all}" -experiment-name "${EXPERIMENT:-en_vs_zh_ai}" -n "${N:-2000}" \
    -per-file "${PER_FILE:-20}" -ngrams "${NGRAMS:-1}" -alpha0 "${ALPHA0:-1000}" ${THRESHOLD:+-threshold "$THRESHOLD"} \
    -selection "${SELECTION:-all}" ${PATTERN:+-pattern "$PATTERN"} ${FROM:+-from "$FROM"} ${TO:+-to "$TO"} \
    ${IDS:+-ids "$IDS"}
