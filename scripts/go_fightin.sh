#!/bin/bash
# Submit every Fightin' Words experiment: each selection in config/fightin_selections.tsv at 1k, 5k and 20k
# documents per language, one job each (results/fightin/<selection>_<n>k/; they don't collide, so they run side by
# side). The small samples finish first, to look at while the 20k ones run. Rerunning is cheap: samples and
# embeddings are reused, only the comparison and plot are redone. An experiment whose job is still queued or running
# is skipped, so a rerun never puts two jobs on one folder.
#   bash scripts/go_fightin.sh                  (from the repo root, on a login node)
#   bash scripts/go_fightin.sh openai anthropic # only these selections
#   NGRAMS=1 bash scripts/go_fightin.sh         # words instead of phrases, on the same samples
#   WINDOW=200 bash scripts/go_fightin.sh anthropic   # only words within 200 of a mention (scripts/go_fightin_window.sh)
# A job of the same experiment (same selection and size, e.g. its whole-document run) still queued or running
# shares its sample: the new job waits for it to end, so the two never sample at once.
set -eo pipefail
SIZES="1000 5000 20000"
mkdir -p logs/scripts/slurm
active=$(squeue -u "$USER" -h -o '%200j' | sed 's/^ *//; s/ *$//')   # full job names
SELECTIONS=${*:-$(grep -v '^#' config/fightin_selections.tsv | tail -n +2 | cut -f1)}
for SELECTION in $SELECTIONS; do
    for N in $SIZES; do
        experiment="fightin_${SELECTION}_$((N / 1000))k"
        name="$experiment${WINDOW:+_w$WINDOW}"
        if grep -qx "$name" <<< "$active"; then
            echo "skipped  $SELECTION  $N  (job $name still queued or running)"
            continue
        fi
        # jobs of the same experiment (it or its window runs) still queued or running: wait for them
        same=$(squeue -u "$USER" -h -o '%i %200j' | awk -v e="$experiment" '$2 == e || index($2, e "_w") == 1 {print $1}' | paste -sd: -)
        job=$(sbatch --parsable --job-name="$name" ${same:+--dependency=afterany:$same} \
              --export=SELECTION=$SELECTION,N=$N,NGRAMS=${NGRAMS:-2-3},WINDOW=${WINDOW:-0} scripts/slurm/fightin.slurm)
        echo "$job  $SELECTION  $N${WINDOW:+  window $WINDOW}  -> results/fightin/${SELECTION}_$((N / 1000))k/${same:+  (after $same)}   log: logs/scripts/slurm/${name}_$job.out"
    done
done
echo "watch: squeue -u $USER | grep fightin"
