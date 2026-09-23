#!/bin/bash
# Go: update the cc conda env, write the TODO list of CC-NEWS WARCs, launch the workers.
# Safe to rerun: done WARCs (.done files in $TMP/warcs) are left out of the TODO list.
# Run from the repo root on a login node.
#
# Usage:
#   START_DATE=20260901 END_DATE=20260923 bash scripts/cc_go.sh
#   START_DATE=20260901 END_DATE=20260923 N_WORKERS=20 bash scripts/cc_go.sh
#   START_DATE=20260923 END_DATE=20260923 N_WORKERS=1 MAX_WARCS=1 MAX_N=100 bash scripts/cc_go.sh  # test

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars

if [ -z "${START_DATE:-}" ] || [ -z "${END_DATE:-}" ]; then
    echo "ERROR: START_DATE and END_DATE (YYYYMMDD) are required"
    echo "Usage: START_DATE=20260901 END_DATE=20260923 bash scripts/cc_go.sh"
    exit 1
fi
N_WORKERS=${N_WORKERS:-10}
ENV_NAME=cc
ENV_FILE=config/cc.yml
AWS=/home/abha4861/bin/v2/2.5.4/bin/aws  # aws CLI v2 on Alpine (an alias there, so not on PATH in jobs)

source ~/.myrc
module load anaconda
if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set; .lock/.done files go in \$TMP/warcs"
    exit 1
fi
WORK_DIR=$TMP/warcs

echo "== env: ${ENV_NAME} from ${ENV_FILE}"
if conda env list | grep -q "^${ENV_NAME} "; then
    conda env update -n "$ENV_NAME" -f "$ENV_FILE" --prune
else
    conda env create -f "$ENV_FILE"
fi
conda activate "$ENV_NAME"

echo "== todo"
TODO_ARGS=(-step todo -start-date "$START_DATE" -end-date "$END_DATE" -aws "$AWS" -work-dir "$WORK_DIR")
[ -n "${MAX_N:-}" ] && TODO_ARGS+=(-max-n "$MAX_N")
python src/cc.py "${TODO_ARGS[@]}"
N_TODO=$(wc -l < "$WORK_DIR/todo.txt")
if [ "$N_TODO" -eq 0 ]; then
    echo "Nothing to do: every WARC in range has a .done file"
    exit 0
fi

N_LAUNCH=$(( N_TODO < N_WORKERS ? N_TODO : N_WORKERS ))
echo "== launch ${N_LAUNCH} workers for ${N_TODO} WARCs"
EXPORTS="AWS=${AWS},TMP=${TMP}"
[ -n "${MAX_N:-}" ] && EXPORTS+=",MAX_N=${MAX_N}"
[ -n "${MAX_WARCS:-}" ] && EXPORTS+=",MAX_WARCS=${MAX_WARCS}"
[ -n "${OUTPUT_DIR:-}" ] && EXPORTS+=",OUTPUT_DIR=${OUTPUT_DIR}"
for i in $(seq 1 "$N_LAUNCH"); do
    sbatch --parsable --export="$EXPORTS" scripts/slurm/cc.slurm
done

echo
echo "Spot checks:"
echo "  squeue -u \$USER -n cc"
echo "  ls $WORK_DIR/*.done | wc -l      # vs $(wc -l < "$WORK_DIR/todo.txt" | tr -d ' ') todo at launch"
echo "  ls $WORK_DIR/*.lock              # in progress (stale if no job is running)"
