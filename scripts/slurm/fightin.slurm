#!/bin/bash
# Fightin' Words between English (CC-NEWS) and Chinese (site crawls) AI coverage (scripts/fightin.py): one job does
# everything. Samples 20k AI documents per language (reused if already sampled), counts phrases of 2-3 words, embeds
# them (reused if unchanged), then for every selection in config/fightin_selections.tsv (all, OpenAI, Anthropic ...)
# writes the comparison and its plot. Edit that file to add selections, then sbatch again.
# Outputs: results/fightin/en_vs_zh_ai_<N in thousands>k/ (one folder per sample size: runs never collide).
#
# Usage (from the repo root):
#   sbatch scripts/slurm/fightin.slurm
#   sbatch --export=NGRAMS=1 scripts/slurm/fightin.slurm              # words instead of phrases, same sample
#   sbatch --export=N=5000 scripts/slurm/fightin.slurm                # another sample size -> en_vs_zh_ai_5k/
#   sbatch --export=STEP=flush,N=20000 scripts/slurm/fightin.slurm    # delete an experiment's outputs

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=fightin
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=48G
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

python -m scripts.fightin -step "${STEP:-all}" -n "${N:-20000}" -ngrams "${NGRAMS:-2-3}" \
    ${EXPERIMENT:+-experiment-name "$EXPERIMENT"}
