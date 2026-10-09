#!/bin/bash
# Step 0 in one go: the two corpora that step 1 (main/step1/go_step1.sh) reads, and what its media storms need.
#   English: CC-NEWS for START_DATE..END_DATE (scripts/go_zh_en.sh): WARCs -> data/interim/cc_html/ (article HTML)
#            -> data/interim/cc_links/ (each article's body links and its "AI" count). No NER (step 1 doesn't
#            need it). Default range: 2023-01-01 to today. Then, for the media storms, after the link workers:
#            the articles' embeddings (scripts/embed_cc_news.sh -> data/interim/cc_news_embeddings/), then their
#            publication dates (scripts/date_cc_news.sh -> data/interim/cc_news_pubdates/).
#   Chinese: the site crawls of config/sites.txt (scrapy/crawl_sites.sh) -> data/interim/site_crawls/<domain>/html/
#            and pages.jsonl; unfinished crawls resume, finished sites are skipped. And the embeddings of the pages
#            crawled so far, for the media storms (scripts/embed_site_crawls.sh -> site_crawls/<domain>/embeddings/;
#            pages crawled later are embedded by the next run).
# Both skip work already done, so rerun it to extend CC-NEWS to new dates or let the crawls continue; then rerun
# step 1. Run from the repo root.
#
# Usage:
#   bash main/step0/go_step0.sh
#   START_DATE=20260301 END_DATE=20261007 bash main/step0/go_step0.sh     # only these CC-NEWS months
#   ONLY=en bash main/step0/go_step0.sh                                  # just CC-NEWS (ONLY=zh: just the crawls)

set -eo pipefail  # no -u: ~/.myrc references unset vars
source ~/.myrc
ONLY=${ONLY:-}

if [ "$ONLY" != zh ]; then
    echo "== English: CC-NEWS ${START_DATE:-20230101}..${END_DATE:-$(date +%Y%m%d)}"
    LINK_JOBS=$(START_DATE=${START_DATE:-20230101} END_DATE=${END_DATE:-$(date +%Y%m%d)} N_NER_WORKERS=0 PARTIAL=1 \
        N_HTML_WORKERS=${N_HTML_WORKERS:-50} N_LINK_WORKERS=${N_LINK_WORKERS:-20} bash scripts/go_zh_en.sh \
        | tee /dev/stderr | sed -n 's/^LINK_JOBS=//p')
    echo
    echo "== English: embeddings, then publication dates (for the media storms)"
    EMBED_JOBS=$(DEPENDENCY=${LINK_JOBS:+afterany:$LINK_JOBS} N_WORKERS=${N_EMBED_WORKERS:-100} \
        bash scripts/embed_cc_news.sh | tee /dev/stderr | sed -n 's/^JOB_IDS=//p')
    DEPENDENCY=afterany:$EMBED_JOBS N_WORKERS=${N_DATE_WORKERS:-200} bash scripts/date_cc_news.sh
    echo
fi
if [ "$ONLY" != en ]; then
    echo "== Chinese: site crawls (config/sites.txt)"
    bash scrapy/crawl_sites.sh
    echo
    echo "== Chinese: embeddings of the pages crawled so far (for the media storms)"
    N_WORKERS=${N_CRAWL_EMBED_WORKERS:-50} bash scripts/embed_site_crawls.sh
fi
echo
echo "When these are done: bash main/step1/go_step1.sh"
