#!/bin/bash
# Everything the Hugging Face / OpenAI agent incident (Jul-Oct 2026) needs for an English and a Chinese storm, as
# one chain of jobs; every step skips work already done.
#   English: embeddings of CC-NEWS WARCs without them -> publication dates -> English storms (REDO_EDGES: days that
#            gained articles from the new months get new edges) -> export
#   Chinese: embeddings of crawl pages without them -> Chinese storms from by_day (files embedded since their split
#            are split again) -> export
#   then:    link_storms (English-Chinese pairs) -> data/processed/storm_links.tsv
#   bash tmp.sh        (from the repo root, on Alpine, after git pull)
set -eo pipefail
source ~/.myrc
mkdir -p logs/scripts/slurm
ids() { sed -n "s/^$1=//p"; }          # the job ids a launcher prints on its last lines

echo "== English: embeddings -> dates"
EMBED=$(N_WORKERS=100 bash scripts/embed_cc_news.sh | tee /dev/stderr | ids JOB_IDS)
DATES=$(DEPENDENCY=afterany:$EMBED N_WORKERS=200 bash scripts/date_cc_news.sh | tee /dev/stderr | ids JOB_IDS)
echo
echo "== English storms, after the dates"
EN_EXPORT=$(AFTER=$DATES REDO_EDGES=1 CORPUS=en bash scripts/go_media_storms.sh | tee /dev/stderr | ids EXPORT_JOB)
echo
echo "== Chinese: crawl-page embeddings -> storms"
ZH_EMBED=$(N_WORKERS=30 bash scripts/embed_site_crawls.sh | tee /dev/stderr | ids JOB_IDS)   # joins any still running
ZH_EXPORT=$(AFTER=$ZH_EMBED FROM=by_day CORPUS=zh bash scripts/go_media_storms.sh | tee /dev/stderr | ids EXPORT_JOB)
echo
LINKS=$(sbatch --parsable --dependency=afterany:$EN_EXPORT:$ZH_EXPORT scripts/slurm/link_storms.slurm)
echo "link_storms $LINKS, after both exports"
echo
echo "Watch: squeue -u \$USER --name=embed_cc_news,date_cc_news,embed_site_crawls,media_storms,export_storms,link_storms -h -o '%j %T' | sort | uniq -c"
echo "Then on the laptop: bash /tmp/pullstorms.sh"
