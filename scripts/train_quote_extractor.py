#!/usr/bin/env python
"""
Train and evaluate the direct-quote extractor (src/quote_extraction) as configured in config/quote_extraction.yaml:
read DirectQuote, split it, fine-tune, pick the best epoch on dev, evaluate on test (seqeval, entity level).
Writes results/train_quote_extractor/<experiment_name>/: model/ (weights + tokenizer), label_map.json,
eval_report.json (test scores per label, split sizes, per-epoch losses, training time), logs/.

Get the data first:  git clone https://github.com/THUNLP-MT/DirectQuote data/external/directquote

Run as a module from the repo root:
    python -m scripts.train_quote_extractor
    python -m scripts.train_quote_extractor -config config/quote_extraction.yaml -max-paragraphs 500   # smoke test
"""
import argparse

import yaml
from transformers import set_seed

from config.paths import REPO_ROOT
from src.quote_extraction.data import read_conll, split_contiguous
from src.token_tagging.encoding import label_list
from src.token_tagging.training import format_summary, load_tokenizer, train_and_save
from src.warc_worker_cli import optional_int

NAME = 'train_quote_extractor'


def parse_args():
    parser = argparse.ArgumentParser(description='Train the DirectQuote quote extractor')
    parser.add_argument('-config', default=str(REPO_ROOT / 'config' / 'quote_extraction.yaml'))
    parser.add_argument('-max-paragraphs', type=optional_int, default=None,
                        help='use only the first N paragraphs (smoke test); adds _maxN to the experiment name')
    return parser.parse_args()


def main():
    args = parse_args()
    with open(args.config) as f:
        config = yaml.safe_load(f)
    experiment = config['experiment_name'] + (f'_max{args.max_paragraphs}' if args.max_paragraphs else '')
    out_dir = REPO_ROOT / 'results' / NAME / experiment
    set_seed(config['training']['seed'])

    paragraphs = read_conll(REPO_ROOT / config['data']['raw_path'])[:args.max_paragraphs]
    splits = split_contiguous(paragraphs, config['data']['train_frac'], config['data']['dev_frac'])
    labels = label_list(paragraphs)
    print(f'{len(paragraphs)} paragraphs: ' + ', '.join(f'{k} {len(v)}' for k, v in splits.items()))

    tokenizer = load_tokenizer(config['model']['base_model'])
    report = train_and_save(splits, labels, tokenizer, config, out_dir, {'experiment': experiment})
    print('\n' + format_summary(report))
    print(f'\ntrained in {report["train_seconds"]}s -> {out_dir}')
    model_dir = out_dir / 'model'
    print('Spot check:')
    print(f"  python -c \"from src.quote_extraction.predict import predict; "
          f"print(predict('\\\"We will keep going,\\\" said Liang Wenfeng.', '{model_dir}'))\"")


if __name__ == '__main__':
    main()
