#!/bin/bash
# Worker for src/cc.py -step work: shuffles $TMP/warcs/todo.txt and processes each WARC not
# done or locked by another worker. Launched by scripts/cc_go.sh, which updates the env, writes
# todo.txt, and submits N of these.
#
# Usage (from the repo root; normally via scripts/cc_go.sh):
#   sbatch --export=AWS=/home/abha4861/bin/v2/2.5.4/bin/aws,TMP=$TMP scripts/slurm/cc.slurm
#   optional: MAX_N=100, MAX_WARCS=1, OUTPUT_DIR=data/interim/cc_links

#SBATCH --partition=amilan
#SBATCH --time=24:00:00
#SBATCH --job-name=cc
#SBATCH --mem=8G
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars

if [ -z "${AWS:-}" ] || [ -z "${TMP:-}" ]; then
    echo "ERROR: AWS (path to aws CLI) and TMP (.lock/.done files go in \$TMP/warcs) are required"
    echo "Usage: sbatch --export=AWS=/home/abha4861/bin/v2/2.5.4/bin/aws,TMP=\$TMP scripts/slurm/cc.slurm"
    exit 1
fi

source ~/.myrc
module load anaconda
conda activate cc

ARGS=(-step work -aws "$AWS" -work-dir "$TMP/warcs")
[ -n "${MAX_N:-}" ] && ARGS+=(-max-n "$MAX_N")
[ -n "${MAX_WARCS:-}" ] && ARGS+=(-max-warcs "$MAX_WARCS")
[ -n "${OUTPUT_DIR:-}" ] && ARGS+=(-output-dir "$OUTPUT_DIR")

python src/cc.py "${ARGS[@]}"
