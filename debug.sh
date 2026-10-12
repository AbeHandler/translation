#!/bin/bash
# Redo tmp4 with the fixed ID search. The tmp4 that ran (33885812) used the old code: its jiemian, yicai and tmtpost
# lists cover the wrong months. This:
#   1. cancels that tmp4 chain only: fetch_urls, embed_site_crawls, the Chinese media_storms/export_storms (ids from
#      33902700; the English storms 33888601-33888604 and the crawls are left alone), check_gold_coverage, debug
#   2. deletes the list fetches' scrapy state of jiemian, yicai and tmtpost (jobdir_urls_*: its queue holds the wrong
#      URLs, and a resumed fetch would carry on with them). ithome's list was right; its fetch resumes.
#   3. submits tmp4.slurm again (new lists, fetches, embeddings, Chinese storms, gold traces)
#   git pull && ./debug.sh        (from the repo root, on Alpine)
set -eo pipefail
git log --oneline -1 | grep -q . && git merge-base --is-ancestor ecf82f3 HEAD \
    || { echo "ERROR: git pull first (needs ecf82f3, the ID-search fix)"; exit 1; }

CANCEL=$(squeue -u "$USER" -h -o '%i %j' | awk '
    $2 ~ /^(fetch_urls|embed_site_crawls|check_gold_coverage|debug|tmp4)$/ ||
    ($2 ~ /^(media_storms|export_storms)$/ && $1 >= 33902700) {print $1}')
echo "cancelling $(wc -w <<< "$CANCEL") jobs of the old tmp4 chain"
[ -n "$CANCEL" ] && scancel $CANCEL
sleep 10   # let cancelled scrapy processes stop writing

for site in jiemian.com yicai.com tmtpost.com; do
    for d in data/interim/site_crawls/$site/jobdir_urls_*; do
        [ -d "$d" ] || continue
        echo "deleting $d"
        find "$d" -type f | shuf | xargs -r rm -f
        rm -rf "$d"
    done
done

sbatch tmp4.slurm
echo "English storms left running: squeue -u \$USER -n media_storms,export_storms,link_storms -o '%i %j %T' | head"
