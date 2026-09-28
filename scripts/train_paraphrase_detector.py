#!/usr/bin/env python
"""
Train and evaluate the paraphrase detector (src/paraphrase_detection) as configured in
config/paraphrase_detection.yaml: read PolNeAR's train/dev/test splits (direct quotes left untagged), fine-tune,
pick the best epoch on dev, evaluate on test (seqeval, entity level). Writes
results/train_paraphrase_detector/<experiment_name>/: model/ (weights + tokenizer), label_map.json,
eval_report.json (test scores per label, split sizes, attribution counts, per-epoch losses, training time), logs/.

Get the data first (~1 GB):  git clone --depth 1 https://github.com/networkdynamics/PolNeAR data/external/polnear

Run as a module from the repo root:
    python -m scripts.train_paraphrase_detector
    python -m scripts.train_paraphrase_detector -max-articles 20   # smoke test
    python -m scripts.train_paraphrase_detector -config config/paraphrase_detection_roberta_base.yaml   # local GPU

The HF Trainer uses a GPU when there is one (CUDA, or MPS on a Mac), else the CPU.
"""
import argparse

import yaml
from transformers import set_seed

from config.paths import REPO_ROOT
from src.paraphrase_detection.polnear import read_split
from src.token_tagging.encoding import label_list
from src.token_tagging.training import format_summary, load_tokenizer, train_and_save
from src.warc_worker_cli import optional_int

NAME = 'train_paraphrase_detector'
SPLITS = ('train', 'dev', 'test')


def parse_args():
    parser = argparse.ArgumentParser(description='Train the PolNeAR paraphrase detector')
    parser.add_argument('-config', default=str(REPO_ROOT / 'config' / 'paraphrase_detection.yaml'))
    parser.add_argument('-max-articles', type=optional_int, default=None,
                        help='use only the first N articles of each split (smoke test); adds _maxN to the '
                             'experiment name')
    return parser.parse_args()


def main():
    args = parse_args()
    with open(args.config) as f:
        config = yaml.safe_load(f)
    experiment = config['experiment_name'] + (f'_max{args.max_articles}' if args.max_articles else '')
    out_dir = REPO_ROOT / 'results' / NAME / experiment
    set_seed(config['training']['seed'])

    splits, counts = {}, {}
    for split in SPLITS:
        splits[split], counts[split] = read_split(REPO_ROOT / config['data']['polnear_dir'], split,
                                                  args.max_articles)
        print(f'{split}: {len(splits[split])} paragraphs, {counts[split]}')
    labels = label_list(splits['train'])

    tokenizer = load_tokenizer(config['model']['base_model'])
    report = train_and_save(splits, labels, tokenizer, config, out_dir,
                            {'experiment': experiment, 'attribution_counts': counts})
    print('\n' + format_summary(report))
    print(f'\ntrained in {report["train_seconds"]}s -> {out_dir}')
    print('Spot check:')
    print(f"  python -c \"from src.paraphrase_detection.predict import predict; "
          f"print(predict('Officials said the talks would resume next week.', '{out_dir / 'model'}'))\"")


if __name__ == '__main__':
    main()
