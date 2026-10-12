#!/bin/bash
# Why the tmp.sh chain (English embed -> dates -> storms -> export -> link_storms) stopped. Read-only.
#   bash debug.sh        (from the repo root, on Alpine)
SINCE=${SINCE:-2026-10-11}
NAMES=embed_cc_news,date_cc_news,embed_site_crawls,media_storms,export_storms,link_storms

echo "== jobs since $SINCE, every state (pending and cancelled too)"
sacct -u "$USER" -S "$SINCE" --name=$NAMES -X -n -o JobName%18,State%25 | sort | uniq -c
echo
echo "== in the queue now"
squeue -u "$USER" -n $NAMES -h -o '%j %T %r' | sort | uniq -c

for name in embed_cc_news date_cc_news media_storms export_storms; do
    failed=$(sacct -u "$USER" -S "$SINCE" --name=$name -X -n -o JobID,State | awk '$2 ~ /FAILED|TIMEOUT|OUT_OF_ME/ {print $1}')
    [ -z "$failed" ] && continue
    echo
    echo "== $name: $(wc -w <<< "$failed") failed; elapsed time of the failures (seconds: failed on start-up)"
    sacct -j "$(paste -sd, <<< "$failed")" -X -n -o Elapsed | sort | uniq -c | sort -rn | head -5
    first=$(head -1 <<< "$failed")
    echo "-- the first failure's log (logs/scripts/slurm/${name}_$first.out), last 15 lines"
    tail -15 "logs/scripts/slurm/${name}_$first.out" 2>/dev/null || echo "   (no log)"
    echo "-- the most common last line among the failures"
    for j in $failed; do tail -1 "logs/scripts/slurm/${name}_$j.out" 2>/dev/null; echo; done \
        | grep -v '^$' | cut -c1-150 | sort | uniq -c | sort -rn | head -5
done

echo
echo "== English progress (files)"
echo "  WARCs:    $(ls data/interim/cc_html | grep -c 'parquet$')"
echo "  embedded: $(ls data/interim/cc_news_embeddings | grep -c 'parquet$')"
echo "  dated:    $(ls data/interim/cc_news_pubdates | grep -c 'parquet$')"
echo "  embedded but not dated (by file name):"
comm -23 <(ls data/interim/cc_news_embeddings | grep 'parquet$' | sort) \
         <(ls data/interim/cc_news_pubdates | grep 'parquet$' | sort) | tee /tmp/undated_$USER.txt | wc -l
head -3 /tmp/undated_$USER.txt

echo
echo "== the newest media_storms and export_storms logs"
ls -t logs/scripts/slurm/media_storms_*.out logs/scripts/slurm/export_storms_*.out 2>/dev/null | head -4 \
    | while read -r f; do echo "-- $f ($(date -r "$f" '+%m-%d %H:%M'))"; tail -4 "$f"; done
