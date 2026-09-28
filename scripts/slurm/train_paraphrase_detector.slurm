#!/bin/bash
# Train the paraphrase (indirect attribution) model (scripts/train_paraphrase_detector.py,
# config/paraphrase_detection.yaml) -> results/train_paraphrase_detector/<experiment_name>/model. Gets the PolNeAR
# data first if it isn't there (github.com/networkdynamics/PolNeAR, ~1 GB). CPU only.
#
# Usage (from the repo root):
#   sbatch --export=NONE scripts/slurm/train_paraphrase_detector.slurm

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=train_paraphrase_detector
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

if [ ! -d data/external/polnear/data/train ]; then
    git clone --depth 1 https://github.com/networkdynamics/PolNeAR data/external/polnear
fi
python -m scripts.train_paraphrase_detector
