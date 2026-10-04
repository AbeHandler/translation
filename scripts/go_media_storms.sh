#!/bin/bash
# Media storms over the embedded and dated English CC-NEWS articles (scripts/media_storms.py), each step waiting
# for the last: N_WORKERS by_day workers, N_WORKERS edges workers, then cluster, storms, seeds, and the export for
# reading (scripts/export_storms.py -> data/processed/storms_review.json; emails when done).
# Rerun after more WARCs are embedded and dated: only new WARCs are split; days that already have edges are kept
# (REDO_EDGES=1 recomputes them, which new articles on old days need). Run from the repo root.
#
# Usage:
#   bash scripts/go_media_storms.sh                 # everything (100 workers per worker step)
#   FROM=storms bash scripts/go_media_storms.sh     # start at a later step: cluster, storms, seeds or export
#   N_WORKERS=1 MAX_FILES=1 bash scripts/go_media_storms.sh   # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
mkdir -p logs/scripts/slurm
N_WORKERS=${N_WORKERS:-100}
FROM=${FROM:-by_day}
STEPS=(by_day edges cluster storms seeds export)
[[ " ${STEPS[*]} " == *" $FROM "* ]] || { echo "FROM must be one of: ${STEPS[*]}" >&2; exit 1; }
started=""
runs() { [[ -n $started || $1 == "$FROM" ]] && started=1; [[ -n $started ]]; }   # runs <step>: at or after FROM?
after() { [[ -n $1 ]] && echo "--dependency=${2:-afterok}$1"; }   # after <ids> [afterany]

workers() {   # workers <step> <cpus> <mem> <dependency ids>: prints :id:id...
    local ids=""
    for ((i = 0; i < N_WORKERS; i++)); do
        ids+=":$(sbatch --parsable ${4:+--dependency=afterany$4} --cpus-per-task="$2" --mem="$3" \
            --export="STEP=$1,MAX_FILES=$MAX_FILES,REDO_EDGES=$REDO_EDGES" scripts/slurm/media_storms.slurm)"
    done
    echo "$ids"
}
one() {       # one <step> <time> <dependency ids> [afterany]: prints :id
    echo ":$(sbatch --parsable $(after "$3" "$4") --cpus-per-task=1 --mem=64G --time="$2" \
        --export="STEP=$1" scripts/slurm/media_storms.slurm)"
}

dep=""
if runs by_day;  then dep=$(workers by_day 1 8G "$dep"); fi
if runs edges;   then dep=$(workers edges 8 32G "$dep"); fi
if runs cluster; then dep=$(one cluster 08:00:00 "$dep" afterany); fi   # workers may end by time limit
if runs storms;  then dep=$(one storms 08:00:00 "$dep"); STORMS=${dep#:}; fi
if runs seeds;   then dep=$(one seeds 12:00:00 "$dep"); SEEDS=${dep#:}; fi
EXPORT=$(sbatch --parsable $(after "$dep") --export=NONE scripts/slurm/export_storms.slurm)
echo "media_storms from $FROM; the export ($EXPORT) emails when done"
echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=media_storms,export_storms"
[[ -n $STORMS ]] && echo "  tail -25 logs/scripts/slurm/media_storms_$STORMS.out   # the storms, largest first"
[[ -n $SEEDS ]] && echo "  tail -25 logs/scripts/slurm/media_storms_$SEEDS.out   # storms most focused on one document"
echo "  cat logs/scripts/slurm/export_storms_$EXPORT.out"
echo "Then on the laptop: bash ~/translation/tmp.sh"
