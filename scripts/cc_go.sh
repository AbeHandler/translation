#!/bin/bash
# Go: submit the whole pipeline to SLURM and return right away.
#   cc_env   create/update the translation conda env from config/translation.yml
#   cc_todo  write $TMP/warcs/todo.txt (WARCs in range without a .done file)   [after cc_env]
#   cc_work  N_WORKERS workers that process todo.txt                            [after cc_todo]
# If a step fails, the jobs after it are cancelled. Safe to rerun: done WARCs are skipped.
# Run from the repo root.
#
# Usage:
#   START_DATE=20260901 END_DATE=20260923 bash scripts/cc_go.sh
#   START_DATE=20260901 END_DATE=20260923 N_WORKERS=20 bash scripts/cc_go.sh
#   START_DATE=20260923 END_DATE=20260923 N_WORKERS=1 MAX_WARCS=1 MAX_N=100 bash scripts/cc_go.sh  # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc  # first, so $TMP etc. from ~/.myrc are set before the checks below

if [ -z "${START_DATE:-}" ] || [ -z "${END_DATE:-}" ]; then
    echo "ERROR: START_DATE and END_DATE (YYYYMMDD) are required"
    echo "Usage: START_DATE=20260901 END_DATE=20260923 bash scripts/cc_go.sh"
    exit 1
fi
if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set; .lock/.done files go in \$TMP/warcs"
    exit 1
fi
N_WORKERS=${N_WORKERS:-10}
AWS=/home/abha4861/bin/v2/2.5.4/bin/aws  # aws CLI v2 on Alpine (an alias there, so not on PATH in jobs)
SLURM_DIR=scripts/slurm
WORK_DIR=$TMP/warcs

# Passed to every job. Unset optional vars go through empty, and the jobs ignore empty ones.
EXPORTS="AWS=$AWS,TMP=$TMP,MAX_N=$MAX_N,MAX_WARCS=$MAX_WARCS,OUTPUT_DIR=$OUTPUT_DIR"

ENV_JOB=$(sbatch --parsable "$SLURM_DIR/cc_env.slurm")
echo "cc_env   $ENV_JOB"

TODO_JOB=$(sbatch --parsable --dependency=afterok:"$ENV_JOB" --kill-on-invalid-dep=yes \
    --export="${EXPORTS},START_DATE=${START_DATE},END_DATE=${END_DATE}" "$SLURM_DIR/cc_todo.slurm")
echo "cc_todo  $TODO_JOB (after $ENV_JOB)"

for i in $(seq 1 "$N_WORKERS"); do
    WORK_JOB=$(sbatch --parsable --dependency=afterok:"$TODO_JOB" --kill-on-invalid-dep=yes \
        --export="$EXPORTS" "$SLURM_DIR/cc_work.slurm")
    echo "cc_work  $WORK_JOB (after $TODO_JOB)"
done

echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=cc_env,cc_todo,cc_work"
echo "  wc -l $WORK_DIR/todo.txt           # WARCs to do (after cc_todo runs)"
echo "  ls $WORK_DIR/*.done | wc -l         # finished"
echo "  ls $WORK_DIR/*.lock                 # in progress (stale if no job is running)"
