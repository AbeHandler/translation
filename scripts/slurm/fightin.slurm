#!/bin/bash
# Fightin' Words between English (CC-NEWS) and Chinese (site crawls) AI coverage, on concepts shared via LaBSE
# (scripts/fightin.py). STEP=all (the default) runs sample, words, embed, fight, plot in order: the slow steps skip
# if their output exists (a rerun picks up where it stopped); fight and plot always rerun. So after any change, just
# sbatch this again. Outputs: results/fightin/<EXPERIMENT>/.
#
# Usage (from the repo root):
#   sbatch scripts/slurm/fightin.slurm
#   sbatch --export=STEP=fight,THRESHOLD=0.7,EXPERIMENT=en_vs_zh_ai scripts/slurm/fightin.slurm   # rerun one step
#   sbatch --export=N=5000,EXPERIMENT=en_vs_zh_ai_5k scripts/slurm/fightin.slurm
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
    -threshold "${THRESHOLD:-0.6}" -alpha0 "${ALPHA0:-1000}"
