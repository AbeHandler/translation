#!/bin/bash
# Train the direct-quote model (scripts/train_quote_extractor.py, config/quote_extraction.yaml) that the CC-NEWS
# quotes step uses -> results/train_quote_extractor/<experiment_name>/model. Gets the DirectQuote data first if
# it isn't there (github.com/THUNLP-MT/DirectQuote; it has no LICENSE file). CPU only: ~1h for ELECTRA-small.
#
# Usage (from the repo root; the env must have been updated since the quote extractor was added):
#   sbatch --export=NONE scripts/slurm/train_quote_extractor.slurm

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=train_quote_extractor
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
#SBATCH --cpus-per-task=16
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

if [ ! -f data/external/directquote/data/truecased.txt ]; then
    git clone --depth 1 https://github.com/THUNLP-MT/DirectQuote data/external/directquote
fi
python -m scripts.train_quote_extractor
