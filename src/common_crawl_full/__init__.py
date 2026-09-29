"""
The regular Common Crawl (the CC-MAIN crawls, not just CC-NEWS), streamed once, keeping English pages that say
"AI". Each WARC is streamed over HTTPS from data.commoncrawl.org and never saved; only its AI pages are, as
<warc name>.ai.warc.gz. There are ~100,000 WARCs per crawl and ~36 crawls since 2023, so workers take WARCs in
random order: whatever gets done is a random sample.

    index.py   the WARC list: every WARC of every crawl since a given year, written to a file once
    filter.py  one WARC -> its English pages that say "AI" (src/ai_mentions.py), as a gzipped WARC
    worker.py  a worker: WARCs from the list in random order, skipping those done or claimed by another worker
    links.py   the AI pages' body links (<warc>.links.jsonl), and their external links for the link queue
"""
