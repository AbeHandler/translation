#!/bin/bash
# The English storms (the tmp.sh chain stopped before them; embeddings and dates are all done), then link_storms.
# REDO_EDGES=1: every day's edges again, with the new March-October articles. The export emails when done.
# Rerun link_storms after tmp4's Chinese export: sbatch scripts/slurm/link_storms.slurm
#   bash debug.sh   or   sbatch debug.sh        (from the repo root, on Alpine)

#SBATCH --partition=acpu
#SBATCH --time=00:30:00
#SBATCH --job-name=debug
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=2G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail
mkdir -p logs/scripts/slurm
EN=$(REDO_EDGES=1 CORPUS=en bash scripts/go_media_storms.sh | tee /dev/stderr | sed -n 's/^EXPORT_JOB=//p')
[ -n "$EN" ] || { echo "ERROR: go_media_storms.sh printed no EXPORT_JOB"; exit 1; }
LINKS=$(sbatch --parsable --dependency=afterany:"$EN" scripts/slurm/link_storms.slurm)
echo "link_storms $LINKS, after the English export $EN"
echo "When done: tail -30 logs/scripts/slurm/link_storms_$LINKS.out"
