#!/bin/bash
# Where the Chinese media storms stand (read-only):
#   1. today's storm jobs that didn't complete, and the error lines of their logs
#   2. edge files, the latest storm step's log tail (clusters passing each test, the 20 largest clusters)
#   3. the storm outputs' sizes
# (Earlier debug scripts are in git history: git log -- debug.slurm.)
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
echo "=== 1. storm jobs since yesterday that didn't complete"
sacct -u "$USER" -S "$(date -d yesterday +%F)" --name=media_storms,export_storms -X \
      -o JobID,JobName%14,State,ExitCode,Elapsed,End | grep -v COMPLETED
echo
echo "error lines in their logs (one line per distinct error, with how many logs have it):"
for id in $(sacct -u "$USER" -S "$(date -d yesterday +%F)" --name=media_storms,export_storms -X -n -o JobID,State \
            | awk '$2 != "COMPLETED" {print $1}'); do
    f=$(ls logs/scripts/slurm/*_"$id".out 2>/dev/null) || continue
    if [ -s "$f" ]; then grep -hE "Error|Exception|Traceback" "$f" | tail -1; else echo "(empty log: died before Python)"; fi
done | sort | uniq -c | sort -rn
echo
echo "=== 2. edges: $(ls $D/edges/ | wc -l) day files ($(ls $D/days/ | wc -l) days of articles)"
LOG=$(ls -t $(grep -l "clusters passing each test" logs/scripts/slurm/media_storms_*.out) | head -1)
echo "the latest storm step's log: $LOG ($(stat -c %y "$LOG" | cut -d. -f1))"
tail -60 "$LOG"
echo
echo "=== 3. outputs"
ls -la $D/clusters.parquet $D/storms.jsonl $D/storm_seeds.jsonl data/processed/storms_review_zh.json
echo "storms: $(wc -l < $D/storms.jsonl)"
