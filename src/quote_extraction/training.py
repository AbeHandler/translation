"""Fine-tuning and evaluation with the HF Trainer. Metrics are entity-level (seqeval, strict IOB2)."""
import numpy as np
from datasets import Dataset
from seqeval.metrics import classification_report
from seqeval.scheme import IOB2
from transformers import (AutoModelForTokenClassification, DataCollatorForTokenClassification, EarlyStoppingCallback,
                          Trainer, TrainingArguments)

from src.quote_extraction.encoding import IGNORE, encode


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
