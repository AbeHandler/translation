#!/bin/bash
# FLUSH: deletes everything the CC-NEWS pipeline (scripts/go.sh) writes, for a clean rerun:
#   $TMP/extract_warc_html/                .lock/.done files of the html step
#   $TMP/find_seed_links/                  .lock/.done files of the old (pre-steps) pipeline, if any
#   $TMP/cc_news_warcs/                    the WARC cache, ONLY with FLUSH_WARCS=1 (kept by default, since
#                                          re-downloading is slow; Alpine purges scratch anyway)
#   data/interim/cc_html/                  raw article HTML Parquet, one per WARC
#   data/interim/cc_links/                 links jsonl, one per WARC
#   data/interim/cc_ner/                   text and named entities Parquet, one per WARC
#   $TMP/download_warcs/                   .lock/.done files of the download step
#   data/processed/cc_link_matches*.jsonl  seed matches
#   data/processed/gazetteer_stories*.jsonl stories naming gazetteer entries
# Submitting it is the confirmation: there is no prompt. Refuses while pipeline jobs are queued or running.
# Deletes files in random order, which spreads the load on the shared filesystem.
#
# Usage (from the repo root):
#   sbatch --export=TMP=$TMP scripts/slurm/flush_cc_news.slurm
#   sbatch --export=TMP=$TMP,FLUSH_WARCS=1 scripts/slurm/flush_cc_news.slurm   # also the cached WARCs

#SBATCH --partition=acpu
#SBATCH --time=24:00:00
#SBATCH --job-name=flush_cc_news
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=4G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set"
    exit 1
fi
JOBS=update_env,cc_news_download,cc_news_html,cc_news_links,cc_news_ner,filter_by_gazetteer,cc_news_match,report_run_done
if [ -n "$(squeue -h -u "$USER" --name=$JOBS)" ]; then
    echo "ERROR: pipeline jobs are still queued/running; scancel them first:"
    squeue -u "$USER" --name=$JOBS
    exit 1
fi

DIRS=("$TMP/extract_warc_html" "$TMP/download_warcs" "$TMP/find_seed_links" data/interim/cc_html data/interim/cc_links
      data/interim/cc_ner)
if [ "${FLUSH_WARCS:-}" = 1 ]; then
    DIRS+=("$TMP/cc_news_warcs")
fi
echo "WARNING: deleting:"
printf '  %s/\n' "${DIRS[@]}"
echo "  data/processed/cc_link_matches*.jsonl data/processed/gazetteer_stories*.jsonl"
for dir in "${DIRS[@]}"; do
    if [ -d "$dir" ]; then
        find "$dir" -type f | shuf | xargs -r rm -f
        find "$dir" -type d -empty -delete
        echo "  deleted $dir/"
    fi
done
rm -f data/processed/cc_link_matches*.jsonl data/processed/gazetteer_stories*.jsonl
echo "Flushed"
