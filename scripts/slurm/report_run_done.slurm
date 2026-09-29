#!/bin/bash
# Runs after the CC-NEWS pipeline's last steps (cc_news_match, cc_news_ner) have ended, success or not, and emails once,
# so a run of many workers sends one "done" email. Prints a summary to its log. Submitted by scripts/go_zh_en.sh.
#
# Usage (from the repo root; normally via scripts/go_zh_en.sh):
#   sbatch --export=NONE --dependency=afterany:<match job id> scripts/slurm/report_run_done.slurm

#SBATCH --partition=acpu
#SBATCH --time=00:10:00
#SBATCH --job-name=report_run_done
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=1G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc

MATCHES=data/processed/cc_link_matches.jsonl

echo "WARCs with HTML:    $(find "$TMP/extract_warc_html" -name '*.done' ! -name '*.max*' 2>/dev/null | wc -l)"
echo "  still locked:     $(find "$TMP/extract_warc_html" -name '*.lock' 2>/dev/null | wc -l)   # >0 means a worker died mid-WARC"
echo "WARCs with links:   $(find data/interim/cc_links -name '*.jsonl' ! -name '*.max*' 2>/dev/null | wc -l)"
echo "  still locked:     $(find data/interim/cc_links -name '*.lock' 2>/dev/null | wc -l)"
if [ -f "$MATCHES" ]; then
    echo "WARCs with entities: $(find data/interim/cc_ner -name '*.parquet' ! -name '*.max*' 2>/dev/null | wc -l)"
echo "Gazetteer stories:   $(wc -l < data/processed/gazetteer_stories.jsonl 2>/dev/null || echo none)"
echo "  their quotes:      $(wc -l < data/processed/gazetteer_quotes.jsonl 2>/dev/null || echo none)"
echo "Seed-link matches:  $(wc -l < "$MATCHES")  ($MATCHES, $(stat -c %y "$MATCHES" | cut -d. -f1))"
else
    echo "WARCs with entities: $(find data/interim/cc_ner -name '*.parquet' ! -name '*.max*' 2>/dev/null | wc -l)"
echo "Gazetteer stories:   $(wc -l < data/processed/gazetteer_stories.jsonl 2>/dev/null || echo none)"
echo "  their quotes:      $(wc -l < data/processed/gazetteer_quotes.jsonl 2>/dev/null || echo none)"
echo "Seed-link matches:  none written (see logs/scripts/slurm/cc_news_match_*.out)"
fi
echo "Cached WARCs:       $(find "$TMP/cc_news_warcs" -name '*.warc.gz' 2>/dev/null | wc -l)  ($(du -sh "$TMP/cc_news_warcs" 2>/dev/null | cut -f1))"
