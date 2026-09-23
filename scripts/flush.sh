#!/bin/bash
# FLUSH: deletes everything the pipeline (scripts/go.sh) writes, for a clean rerun:
#   $TMP/find_seed_links/                  downloaded WARCs and .lock/.done files
#   data/interim/cc_links/                 links jsonl, one per WARC
#   data/processed/cc_link_matches*.jsonl  seed matches
#   logs/scripts/slurm/{update_env,find_seed_links}_*.out
# Refuses while pipeline jobs are queued or running. Run from the repo root.
#
# Usage:
#   bash scripts/flush.sh          # asks before deleting
#   FORCE=1 bash scripts/flush.sh  # no prompt

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set"
    exit 1
fi
if command -v squeue >/dev/null && [ -n "$(squeue -h -u "$USER" --name=update_env,find_seed_links)" ]; then
    echo "ERROR: pipeline jobs are still queued/running; scancel them first:"
    squeue -u "$USER" --name=update_env,find_seed_links
    exit 1
fi

DIRS=("$TMP/find_seed_links" data/interim/cc_links)
FILES=(data/processed/cc_link_matches*.jsonl logs/scripts/slurm/update_env_*.out logs/scripts/slurm/find_seed_links_*.out)

echo "WARNING: this deletes:"
printf '  %s/\n' "${DIRS[@]}"
printf '  %s\n' "${FILES[@]}"
if [ "${FORCE:-}" != 1 ]; then
    read -r -p "Continue? [y/N] " answer
    [ "$answer" = y ] || { echo "Aborted"; exit 1; }
fi

for dir in "${DIRS[@]}"; do
    if [ -d "$dir" ]; then
        # random order spreads the I/O load on the shared filesystem
        find "$dir" -type f | shuf | xargs -r rm -f
        find "$dir" -type d -empty -delete
        echo "  deleted $dir/"
    fi
done
for f in "${FILES[@]}"; do
    if [ -e "$f" ]; then rm -f "$f"; fi
done
echo "Flushed"
