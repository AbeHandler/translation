#!/bin/bash
# Report on how well the site crawls find articles about Dario Amodei's 'We Must Pace the Frontier'
# (tmp.py): tmp_report.md (per-site coverage of 2026-09-12..19, and what each way of finding them turns up)
# and tmp.jsonl (the candidate articles). Safe while the crawls run; it only reads.
#
# Usage (from the repo root):
#   sbatch tmp.slurm

#SBATCH --partition=acpu
#SBATCH --time=04:00:00
#SBATCH --job-name=tmp
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=16G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

python tmp.py
