"""Fine-tuning and evaluation with the HF Trainer. Metrics are entity-level (seqeval, strict IOB2)."""
import json
import os
import time

import numpy as np
from datasets import Dataset
from seqeval.metrics import classification_report
from seqeval.scheme import IOB2
from transformers import (AutoModelForTokenClassification, AutoTokenizer, DataCollatorForTokenClassification,
                          EarlyStoppingCallback, Trainer, TrainingArguments)

from src.token_tagging.encoding import IGNORE, encode


def load_tokenizer(base_model):
    """add_prefix_space: BPE tokenizers (RoBERTa, GPT-2) need it for pre-split words; WordPiece ignores it."""
    return AutoTokenizer.from_pretrained(base_model, add_prefix_space=True)


def to_tag_sequences(predictions, label_ids, id2label):
    """Drop ignored positions; ids -> tags."""
    true, pred = [], []
    for p_row, l_row in zip(predictions, label_ids):
        keep = [(p, l) for p, l in zip(p_row, l_row) if l != IGNORE]
        true.append([id2label[l] for _, l in keep])
        pred.append([id2label[p] for p, _ in keep])
    return true, pred


def seqeval_report(true, pred):
    """{label: {precision, recall, f1, support}, 'micro avg': ..., ...}"""
    report = classification_report(true, pred, mode='strict', scheme=IOB2, output_dict=True, zero_division=0)
    return {label: {k: float(v) for k, v in scores.items()} for label, scores in report.items()}


def make_compute_metrics(id2label):
    def compute_metrics(eval_prediction):
        predictions = np.argmax(eval_prediction.predictions, axis=-1)
        report = seqeval_report(*to_tag_sequences(predictions, eval_prediction.label_ids, id2label))
        micro = report['micro avg']
        return {'precision': micro['precision'], 'recall': micro['recall'], 'f1': micro['f1-score']}
    return compute_metrics


def train_and_evaluate(splits, tokenizer, labels, config, model_dir, log_dir):
    """Fine-tune on train, pick the best epoch on dev, evaluate on test. Returns (trainer, report)."""
    label2id = {label: i for i, label in enumerate(labels)}
    id2label = dict(enumerate(labels))
    max_length = config['model']['max_seq_length']
    datasets, truncated = {}, {}
    for name, paragraphs in splits.items():
        encoded, truncated[name] = encode(paragraphs, tokenizer, label2id, max_length)
        datasets[name] = Dataset.from_dict(encoded)
    model = AutoModelForTokenClassification.from_pretrained(
        config['model']['base_model'], num_labels=len(labels), id2label=id2label, label2id=label2id)
    t = config['training']
    args = TrainingArguments(
        output_dir=str(model_dir) + '_checkpoints', logging_dir=str(log_dir), num_train_epochs=t['epochs'],
        per_device_train_batch_size=t['batch_size'], per_device_eval_batch_size=t['batch_size'],
        learning_rate=float(t['learning_rate']), weight_decay=t['weight_decay'], warmup_ratio=t['warmup_ratio'],
        eval_strategy=t['eval_strategy'], save_strategy=t['save_strategy'], logging_strategy=t['eval_strategy'],
        load_best_model_at_end=True, metric_for_best_model=t['metric_for_best_model'], greater_is_better=True,
        save_total_limit=2, seed=t['seed'], report_to=[])
    trainer = Trainer(model=model, args=args, train_dataset=datasets['train'], eval_dataset=datasets['dev'],
                      data_collator=DataCollatorForTokenClassification(tokenizer),
                      compute_metrics=make_compute_metrics(id2label),
                      callbacks=[EarlyStoppingCallback(early_stopping_patience=t['early_stopping_patience'])])
    trainer.train()
    output = trainer.predict(datasets['test'])
    test = seqeval_report(*to_tag_sequences(np.argmax(output.predictions, axis=-1), output.label_ids, id2label))
    return trainer, {'test': test, 'truncated_paragraphs': truncated,
                     'log_history': trainer.state.log_history, 'best_checkpoint': trainer.state.best_model_checkpoint}


def train_and_save(splits, labels, tokenizer, config, out_dir, extra_report=None):
    """train_and_evaluate, then write out_dir/: model/ (weights + tokenizer), label_map.json, eval_report.json
    (test scores per label, split sizes, per-epoch losses, training time, plus extra_report), logs/. Returns the
    report."""
    model_dir, log_dir = out_dir / 'model', out_dir / 'logs'
    os.makedirs(log_dir, exist_ok=True)
    with open(out_dir / 'label_map.json', 'w') as f:
        json.dump({label: i for i, label in enumerate(labels)}, f, indent=2)
    started = time.time()
    trainer, report = train_and_evaluate(splits, tokenizer, labels, config, model_dir, log_dir)
    trainer.save_model(str(model_dir))
    tokenizer.save_pretrained(str(model_dir))
    report.update(config=config, labels=labels, train_seconds=round(time.time() - started),
                  split_sizes={k: len(v) for k, v in splits.items()}, **(extra_report or {}))
    with open(out_dir / 'eval_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    return report


def format_summary(report):
    """The test scores as a table."""
    lines = [f'{"label":16} {"precision":>9} {"recall":>7} {"f1":>7} {"support":>8}']
    for label, s in report['test'].items():
        lines.append(f'{label:16} {s["precision"]:9.3f} {s["recall"]:7.3f} {s["f1-score"]:7.3f} '
                     f'{int(s["support"]):8d}')
    return '\n'.join(lines)
