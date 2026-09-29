# translation

Common Crawl's CC-NEWS barely covers mainland Chinese outlets (many block or never appear in it), so there are
two collection pipelines: CC-NEWS, and our own crawl of Chinese sites. Integrating them comes later.

## Drivers (run from the repo root on Alpine; each submits SLURM jobs and returns)

- `scripts/go_zh_en.sh` — CC-NEWS for a date range: download WARCs → raw HTML → body links + spaCy NER →
  seed-link matches (`config/seed_patterns.txt`), gazetteer stories (`config/gazetteer.yaml`), and the direct
  quotes (with speakers) in those stories.
  `START_DATE=20260223 END_DATE=20260302 bash scripts/go_zh_en.sh`
- `scripts/go_en_zh.sh` — crawl the Chinese sites in `config/sites.txt` (links and sitemaps), then embed the
  pages and build an Annoy index. `bash scripts/go_en_zh.sh`
- `scripts/run_translations.py` — machine translation (runs locally; API keys in `.env`): fetch the documents in
  `config/mt_sources.yaml`, queue them, translate with every engine into `data/processed/translations.sqlite`.
  `python -m scripts.run_translations -engines grok -dry-run`

- `scripts/go_wikipedia.sh` — Wikipedia (zh, en) from the dumps: every article saying "AI" → a filter
  (`config/wikipedia.yaml`) → their external links as a queue of `{srcpage, url}` shards in `$TMP/wikipedia_queue/`.
- `scripts/process_queue.sh` — process any shard queue with many SLURM workers (`src/shard_queue`; processors
  are named in `scripts/process_queue.py`, e.g. `link_language`: fetch each link and label its language,
  `src/link_language`). `scripts/cc_news_queue.py` builds the queue of CC-NEWS AI articles' external links.

Every step skips work already done, so any driver can be stopped and rerun.

## Steps (each also runs on its own; usage at the top of each file)

- `scripts/cc_news_pipeline.py -step download|html|links|ner|match` — the CC-NEWS steps
  (`scripts/slurm/cc_news_pipeline.slurm`).
- `scripts/train_quote_extractor.py` — the direct-quote model (DirectQuote, `config/quote_extraction.yaml`) used by
  by `scripts/extract_quotes.py` on the gazetteer stories → `data/processed/gazetteer_quotes.jsonl`;
  `scripts/slurm/train_quote_extractor.slurm` trains it on Alpine.
- `scripts/train_paraphrase_detector.py` — the paraphrase (indirect attribution) model: Source / Cue / Content
  tags trained on PolNeAR (`config/paraphrase_detection*.yaml`), direct quotes left to the quote extractor.
  Trained locally on the GPU; the model is rsynced to Alpine for CPU inference. Both models share
  `src/token_tagging`.
- `scripts/filter_by_gazetteer.py` — stories naming gazetteer entries → `data/processed/gazetteer_stories.jsonl`.
- `scrapy/crawl_sites.sh` — one crawl job per site (`scrapy/slurm/crawl_site.slurm`).
- `scripts/embed_site_crawls.sh` — bge-base-zh embeddings of crawled pages.
- `scripts/slurm/build_annoy_index.slurm` — one Annoy index over the embeddings.
- `scripts/slurm/update_env.slurm` — the `translation` conda env from `config/requirements.txt`.
- `scripts/slurm/flush_cc_news.slurm`, `scrapy/slurm/flush_crawls.slurm` — delete a pipeline's outputs.
- `tmp.py` / `tmp.slurm` — coverage report for specific source posts (temporary).

## Data

- `data/interim/cc_html|cc_links|cc_ner/<warc>` — CC-NEWS, one file per WARC (WARCs cached in `$TMP/cc_news_warcs`).
- `data/interim/site_crawls/<domain>/` — `pages.jsonl`, `html/`, `embeddings/` per crawled site.
- `data/processed/` — matches, gazetteer stories, the Annoy index, the translations database.

Code layout: `src/` is logic, `scripts/` runs it, `config/` holds paths and inputs, `test/` runs with
`python -m pytest test/`.
