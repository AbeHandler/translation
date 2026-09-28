#!/bin/bash
# Driver for the CC-NEWS pipeline (scripts/cc_news_pipeline.py): submits every step to SLURM, each after the
# one before it, and returns right away.
#   update_env       create the translation conda env and pip install config/requirements.txt
#   cc_news_html     N_HTML_WORKERS workers: WARCs -> data/interim/cc_html/<warc>.parquet (raw en/zh HTML).
#                    The only step that reads WARCs (cached in $TMP/cc_news_warcs and kept).
#   cc_news_links    N_LINK_WORKERS workers, after the html workers: cc_html -> data/interim/cc_links/<warc>.jsonl
#   cc_news_ner      N_NER_WORKERS workers (8 CPUs, 16G each), also after the html workers: cc_html ->
#                    data/interim/cc_ner/<warc>.parquet, each English article's text and spaCy entities
#   cc_news_match    one job, after the links workers: -> data/processed/cc_link_matches.jsonl (the seeds in
#                    config/seed_patterns.txt). Fails if some WARC in the range still has no links file.
#   report_run_done  after the match and ner: a summary and the one "done" email. The rest emails on failure.
# DOWNLOAD_ONLY=1 instead just fetches the range's WARCs into $TMP/cc_news_warcs (N_DOWNLOAD_WORKERS workers),
# ahead of the html step; they are scratch and can be deleted whenever.
# Safe to rerun: every step skips work already done. A new seed pattern only needs the match step (MATCH_ONLY=1).
# Clean slate: sbatch --export=NONE scripts/slurm/flush_cc_news.slurm. Logs: logs/scripts/slurm/<job>_<id>.out.
# Run from the repo root.
#
# Usage:
#   START_DATE=20260901 END_DATE=20260923 bash scripts/go.sh
#   START_DATE=20260901 END_DATE=20260923 N_HTML_WORKERS=20 N_LINK_WORKERS=20 bash scripts/go.sh
#   START_DATE=20260901 END_DATE=20260923 MATCH_ONLY=1 bash scripts/go.sh      # rematch, e.g. after a new seed
#   START_DATE=20260901 END_DATE=20260923 DOWNLOAD_ONLY=1 bash scripts/go.sh   # just download the WARCs
#   START_DATE=20260901 END_DATE=20260923 N_NER_WORKERS=0 bash scripts/go.sh   # skip NER
#   START_DATE=20260923 END_DATE=20260923 N_HTML_WORKERS=1 N_LINK_WORKERS=1 MAX_WARCS=1 MAX_N=100 PARTIAL=1 bash scripts/go.sh  # test

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc  # first, so $TMP etc. from ~/.myrc are set before the checks below

if [ -z "${START_DATE:-}" ] || [ -z "${END_DATE:-}" ]; then
    echo "ERROR: START_DATE and END_DATE (YYYYMMDD) are required"
    echo "Usage: START_DATE=20260901 END_DATE=20260923 bash scripts/go.sh"
    exit 1
fi
for d in "$START_DATE" "$END_DATE"; do
    if ! [[ $d =~ ^20[0-9]{6}$ ]] || ! date -d "$d" >/dev/null 2>&1; then
        echo "ERROR: dates must be YYYYMMDD (e.g. 20260223), not '$d'"
        exit 1
    fi
done
if [ "$START_DATE" -gt "$END_DATE" ]; then
    echo "ERROR: START_DATE $START_DATE is after END_DATE $END_DATE"
    exit 1
fi
N_DAYS=$(( ($(date -d "$END_DATE" +%s) - $(date -d "$START_DATE" +%s)) / 86400 + 1 ))
MAX_DAYS=${MAX_DAYS:-31}  # CC-NEWS is ~100 1GB WARCs a day: a month is ~3TB of scratch
if [ "$N_DAYS" -gt "$MAX_DAYS" ]; then
    echo "ERROR: $N_DAYS days is about $((N_DAYS / 10))TB of WARCs; run a few weeks at a time,"
    echo "       or set MAX_DAYS=$N_DAYS if scratch really has room."
    exit 1
fi
if [ -z "${TMP:-}" ]; then
    echo "ERROR: \$TMP is not set; the WARC cache and .lock/.done files go there"
    exit 1
fi
N_HTML_WORKERS=${N_HTML_WORKERS:-10}
N_LINK_WORKERS=${N_LINK_WORKERS:-10}
N_NER_WORKERS=${N_NER_WORKERS:-10}
N_DOWNLOAD_WORKERS=${N_DOWNLOAD_WORKERS:-10}
AWS=/home/abha4861/bin/v2/2.5.4/bin/aws  # aws CLI v2 on Alpine (an alias there, so not on PATH in jobs)
mkdir -p logs/scripts/slurm  # SLURM won't create the --output dir

# --export=NONE: without it sbatch copies this shell's environment (--export=ALL), including the
# login node's MODULEPATH, and `module load anaconda` then fails on the compute node.
ENV_JOB=$(sbatch --parsable --export=NONE scripts/slurm/update_env.slurm)
echo "update_env       $ENV_JOB"

# Passed to every step. Unset optional vars go through empty, and the script ignores them.
EXPORTS="START_DATE=$START_DATE,END_DATE=$END_DATE,AWS=$AWS,TMP=$TMP,MAX_N=$MAX_N,MAX_WARCS=$MAX_WARCS,PARTIAL=$PARTIAL"

submit_step() {  # submit_step <step> <how many> <dependency> [more sbatch options]; prints the job ids as :id:id...
    local step=$1 n=$2 dependency=$3 jobs=""
    shift 3
    for ((i = 0; i < n; i++)); do
        jobs+=":$(sbatch --parsable --job-name="cc_news_$step" --dependency="$dependency" --kill-on-invalid-dep=yes \
            --export="STEP=$step,$EXPORTS" "$@" scripts/slurm/cc_news_pipeline.slurm)"
    done
    echo "$jobs"
}

AFTER=afterok:$ENV_JOB
if [ "${DOWNLOAD_ONLY:-}" = 1 ]; then
    submit_step download "$N_DOWNLOAD_WORKERS" "$AFTER" > /dev/null
    echo "cc_news_download $N_DOWNLOAD_WORKERS workers (after $ENV_JOB) -> $TMP/cc_news_warcs"
    echo "  ls $TMP/download_warcs/*.done | wc -l; du -sh $TMP/cc_news_warcs"
    exit 0
fi
NER_JOBS=""
if [ "${MATCH_ONLY:-}" != 1 ]; then
    HTML_JOBS=$(submit_step html "$N_HTML_WORKERS" "$AFTER")
    echo "cc_news_html     $N_HTML_WORKERS workers (after $ENV_JOB)"
    # afterany: a worker hitting its time limit shouldn't block the rest; the next step checks what's done
    LINK_JOBS=$(submit_step links "$N_LINK_WORKERS" "afterany$HTML_JOBS")
    echo "cc_news_links    $N_LINK_WORKERS workers (after the html workers)"
    NER_JOBS=$(submit_step ner "$N_NER_WORKERS" "afterany$HTML_JOBS" --cpus-per-task=8 --mem=16G)
    echo "cc_news_ner      $N_NER_WORKERS workers (after the html workers)"
    AFTER=afterany$LINK_JOBS
fi
MATCH_JOB=$(submit_step match 1 "$AFTER")
echo "cc_news_match    ${MATCH_JOB#:}"

REPORT_JOB=$(sbatch --parsable --dependency=afterany"$MATCH_JOB$NER_JOBS" --export="TMP=$TMP" \
    scripts/slurm/report_run_done.slurm)
echo "report_run_done  $REPORT_JOB (after the match and ner)"

echo
echo "Spot checks:"
echo "  squeue -u \$USER --name=update_env,cc_news_html,cc_news_links,cc_news_ner,cc_news_match,report_run_done"
echo "  ls $TMP/extract_warc_html/*.done | wc -l      # WARCs with HTML"
echo "  ls data/interim/cc_links/*.jsonl | wc -l      # WARCs with links"
echo "  ls data/interim/cc_ner/*.parquet | wc -l      # WARCs with entities"
echo "  ls $TMP/extract_warc_html/*.lock data/interim/cc_links/*.lock   # in progress (stale if no job runs)"
echo "  tail logs/scripts/slurm/cc_news_*_*.out"
