#!/bin/bash
# Chinese media storms from everything the site crawls have saved so far, in one go: embed the crawled pages that
# have no embeddings yet (scripts/embed_site_crawls.sh: update_env, then N_EMBED workers), then, once those
# workers end, every storm step over the Chinese AI pages (CORPUS=zh scripts/go_media_storms.sh: by_day, which
# also dates the pages, edges, cluster, storms, seeds, and the export -> data/processed/storms_review_zh.json,
# which emails when done). Every step skips work already done, so run it again whenever the crawls have saved
# more, or a run was cut short: it does only what is left. Run from the repo root.
#
# Usage:
#   bash scripts/go_media_storms_zh.sh
#   N_EMBED=100 N_WORKERS=200 bash scripts/go_media_storms_zh.sh     # more workers (defaults 50 and 100)
#   FLUSH=1 bash scripts/go_media_storms_zh.sh     # rebuild the storms from scratch (deletes media_storms_zh first)

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

EMBED_JOBS=$(N_WORKERS=${N_EMBED:-50} bash scripts/embed_site_crawls.sh | tee /dev/stderr | sed -n 's/^JOB_IDS=//p')
[[ -n $EMBED_JOBS ]] || { echo "ERROR: no embedding jobs were submitted" >&2; exit 1; }
echo
FLUSH=$FLUSH AFTER=$EMBED_JOBS CORPUS=zh N_WORKERS=${N_WORKERS:-100} bash scripts/go_media_storms.sh
