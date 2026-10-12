#!/bin/bash
# The Chinese articles the crawls missed, for the Hugging Face / OpenAI agent incident and DeepSeek-R1:
#   1. URL lists (scripts/make_crawl_urls.py): each gold list's articles per site, and for the numbered sites
#      (ithome, jiemian, yicai, tmtpost) every article ID in the event's window, by binary search over the IDs
#   2. one fetch job per site and list (scrapy/fetch_url_lists.sh -> scrapy/slurm/fetch_urls.slurm), into the
#      sites' crawl stores; each emails when done
#   3. after the fetches: embeddings of the new pages (scripts/embed_site_crawls.sh)
#   4. after those: the Chinese storms from by_day (files with new pages are split again) through the export
#   5. after the export: the gold traces for both events and the storm debug
#
# Usage (from the repo root):
#   sbatch tmp4.slurm        # then: cat logs/scripts/slurm/tmp4_<jobid>.out

#SBATCH --partition=acpu
#SBATCH --time=04:00:00
#SBATCH --job-name=tmp4
#SBATCH --output=logs/scripts/slurm/%x_%j.out
#SBATCH --mem=8G
#SBATCH --qos=cpu-normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=abha4861@colorado.edu

set -eo pipefail  # no -u: ~/.myrc and conda activate reference unset vars
source ~/.myrc
module load anaconda
conda activate translation

echo "== URL lists: the Hugging Face / OpenAI agent incident"
python -m scripts.make_crawl_urls -name hf_hack -gold config/gold/chinese_coverage_hf_openai_anthropic.csv \
    -from 2026-07-16 -to 2026-10-08
echo
echo "== URL lists: DeepSeek-R1"
python -m scripts.make_crawl_urls -name r1 -gold config/gold/chinese_coverage_deepseek_r1.csv \
    -from 2025-01-15 -to 2025-02-20
echo
ids() { sed -n "s/^$1=//p"; }          # the job ids a launcher prints on its last line
echo "== fetch jobs"
FETCH=$(NAME=hf_hack bash scrapy/fetch_url_lists.sh | tee /dev/stderr | ids JOB_IDS)
FETCH+=":$(NAME=r1 bash scrapy/fetch_url_lists.sh | tee /dev/stderr | ids JOB_IDS)"
echo
echo "== embeddings of the new pages, after the fetches"
EMBED=$(DEPENDENCY=afterany:$FETCH N_WORKERS=30 bash scripts/embed_site_crawls.sh | tee /dev/stderr | ids JOB_IDS)
echo
echo "== Chinese storms from by_day, after the embeddings"
EXPORT=$(AFTER=$EMBED FROM=by_day CORPUS=zh bash scripts/go_media_storms.sh | tee /dev/stderr | ids EXPORT_JOB)
echo
echo "== gold traces and the storm debug, after the export"
A=$(sbatch --parsable --dependency=afterany:$EXPORT \
    --export=GOLD=config/gold/chinese_coverage_hf_openai_anthropic.csv scripts/slurm/check_gold_coverage.slurm)
B=$(sbatch --parsable --dependency=afterany:$EXPORT \
    --export=GOLD=config/gold/chinese_coverage_deepseek_r1.csv scripts/slurm/check_gold_coverage.slurm)
C=$(sbatch --parsable --dependency=afterany:$EXPORT debug.slurm)
echo "check_gold_coverage $A (OpenAI/HF), $B (DeepSeek-R1); debug $C"
echo
echo "Watch: squeue -u \$USER --name=fetch_urls,embed_site_crawls,media_storms,export_storms,check_gold_coverage,debug -h -o '%j %T' | sort | uniq -c"
echo "When done:"
echo "  tail -14 logs/scripts/slurm/check_gold_coverage_$A.out"
echo "  tail -14 logs/scripts/slurm/check_gold_coverage_$B.out"
echo "  head -60 logs/scripts/slurm/debug_$C.out"
