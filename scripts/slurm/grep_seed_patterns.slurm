#!/bin/bash
# Scan the links jsonl (src/cc.py -step grep) for the substrings in config/seed_patterns.txt
# and write data/processed/cc_link_matches.jsonl. Submitted by scripts/cc_go.sh after the workers.
# Rebuilds the matches file each run, so rerun it any time (e.g. after editing the patterns).
#
# Usage (from the repo root):
#   sbatch scripts/slurm/grep_seed_patterns.slurm
#   optional: MAX_N=100 (grep that test run's files), OUTPUT_DIR=data/interim/cc_links

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=grep_seed_patterns
#SBATCH --mem=4G
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc

module load anaconda
conda activate translation

# Optional vars may be empty; src/cc.py treats empty as "use the default".
python src/cc.py \
    -step grep \
    -patterns config/seed_patterns.txt \
    -max-n "$MAX_N" \
    -output-dir "$OUTPUT_DIR"
