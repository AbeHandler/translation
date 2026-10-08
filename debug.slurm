#!/bin/bash
# Where the Chinese media storms stand (read-only): the storm step's log tail (clusters passing each test, the 20
# largest clusters), and the storm outputs' sizes. (The previous debug script, for the by_day step, is in git
# history: git show 08b518f:debug.slurm.)
#
# Usage (from the repo root):
#   sbatch debug.slurm        # then: cat logs/scripts/slurm/debug_<jobid>.out

#SBATCH --partition=acpu
#SBATCH --time=00:10:00
#SBATCH --job-name=debug
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=1G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

D=data/interim/media_storms_zh
echo "=== edges: $(ls $D/edges/ | wc -l) day files"
LOG=$(ls -t $(grep -l "clusters passing each test" logs/scripts/slurm/media_storms_*.out) | head -1)
echo "=== the latest storm step's log: $LOG"
tail -60 "$LOG"
echo
echo "=== outputs"
ls -la $D/clusters.parquet $D/storms.jsonl $D/storm_seeds.jsonl data/processed/storms_review_zh.json
echo "storms: $(wc -l < $D/storms.jsonl)"
