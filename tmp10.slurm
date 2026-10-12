#!/bin/bash
# The DeepSeek English/Chinese datasets for sharing (scripts/export_paired_dataset.py), from the fightin DeepSeek
# sample (deepseek_20k, else deepseek_5k) -> results/export_paired_dataset/{deepseek_r1,deepseek_all}/
#   sbatch tmp10.slurm        (from the repo root; then: cat logs/scripts/slurm/tmp10_<jobid>.out)

#SBATCH --partition=acpu
#SBATCH --time=00:30:00
#SBATCH --job-name=tmp10
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc
module load anaconda
conda activate translation

EXP=deepseek_20k
[ -f results/fightin/$EXP/docs.parquet ] || EXP=deepseek_5k
[ -f results/fightin/$EXP/docs.parquet ] || { echo "ERROR: no results/fightin/deepseek_{20k,5k}/docs.parquet"; exit 1; }
echo "== from $EXP"
python -m scripts.export_paired_dataset -experiment $EXP -name deepseek_r1 -from 2025-01-15 -to 2025-02-28
python -m scripts.export_paired_dataset -experiment $EXP -name deepseek_all
echo
echo "On the laptop:"
echo "  rsync -av --relative abha4861@login.rc.colorado.edu:$PWD/./results/export_paired_dataset ~/translation/"
