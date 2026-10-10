"""
A checkpoint for a long sampling run, so that a job stopped by its time limit resumes instead of starting over: the
documents found so far (in parquet parts) and the files already read, in one folder. The checkpoint belongs to one
sampling setup (key: e.g. the sampling version, n, the selection); a different key, e.g. after the sampling rules
changed, discards it.
"""
import json
import os
import shutil

import pandas as pd


class SampleCache:
    def __init__(self, folder, key):
        self.folder, self.key = folder, key
        self.progress_path = os.path.join(folder, 'progress.json')
        self.parts = 0

    def load(self):
        """(documents found so far, files done, complete): empty if there's no checkpoint for this key."""
        if not os.path.exists(self.progress_path):
            return [], set(), False
        with open(self.progress_path, encoding='utf-8') as f:
            progress = json.load(f)
        if progress.get('key') != self.key:
            self.clear()
            return [], set(), False
        self.parts = progress['parts']
        docs = []
        for k in range(self.parts):
            docs += pd.read_parquet(os.path.join(self.folder, f'part-{k:05d}.parquet')).to_dict('records')
        return docs, set(progress['done']), progress['complete']

    def save(self, new_docs, done, complete=False):
        """Add the documents found since the last save, and record the files done (atomically)."""
        os.makedirs(self.folder, exist_ok=True)
        if new_docs:
            part = os.path.join(self.folder, f'part-{self.parts:05d}.parquet')
            pd.DataFrame(new_docs).to_parquet(part + '.part')
            os.replace(part + '.part', part)
            self.parts += 1
        with open(self.progress_path + '.part', 'w', encoding='utf-8') as f:
            json.dump({'key': self.key, 'parts': self.parts, 'done': sorted(done), 'complete': complete}, f)
        os.replace(self.progress_path + '.part', self.progress_path)

    def clear(self):
        shutil.rmtree(self.folder, ignore_errors=True)
        self.parts = 0
