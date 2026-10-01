"""
The worker loop for file-to-file steps: many copies can run at once (e.g. as SLURM jobs) over the same files.
Each takes the input files whose output doesn't exist yet, in random order, and claims each with a .lock next
to its output (created atomically, so two workers never take the same file). The lock is removed afterwards,
also when processing fails or the job is cancelled, so a rerun picks the file up. Outputs must be written
atomically (e.g. via a .part file), so an output that exists is complete.
"""
import logging
import os
import random
import socket
import time

logger = logging.getLogger(__name__)


def claim_lock(path):
    """Create the lock file (host and job id inside); False if another worker already has it.
    O_EXCL makes this atomic, also across nodes on the shared filesystem."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, 'w') as f:
        f.write(f'{socket.gethostname()} {slurm_job_id()}\n')
    return True


def slurm_job_id():
    return os.environ.get('SLURM_JOB_ID', f'pid{os.getpid()}')


SHOW_TODO = 100  # the to-do list is logged in full up to this many files


def process_files(in_paths, out_path_of, process, max_files=None):
    """Run process(in_path, out_path) -> info for every input without an output. Returns the number of files
    this worker processed. Logs its to-do list at the start and 'start'/'done' per file, so a file that hangs
    shows as a 'start' without a 'done'."""
    todo = [path for path in in_paths if not os.path.exists(out_path_of(path))]
    random.shuffle(todo)
    logger.info('%d input files, %d without output (this worker\'s to-do list, in its order):', len(in_paths),
                len(todo))
    for path in todo[:SHOW_TODO]:
        logger.info('  todo %s', path)
    if len(todo) > SHOW_TODO:
        logger.info('  ... and %d more', len(todo) - SHOW_TODO)
    n_done = 0
    for n, in_path in enumerate(todo, 1):
        out_path = out_path_of(in_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        if os.path.exists(out_path) or not claim_lock(out_path + '.lock'):
            continue
        logger.info('start %d/%d %s', n, len(todo), in_path)
        started = time.time()
        try:
            info = process(in_path, out_path)
        finally:
            os.remove(out_path + '.lock')
        logger.info('done %s in %.0fs %s', out_path, time.time() - started, info)
        n_done += 1
        if max_files and n_done >= max_files:
            break
    return n_done


def delete_done_inputs(in_paths, out_path_of):
    """Delete each input whose output exists (and isn't locked: still being written), in random order: a cleanup
    for big inputs (WARCs) that nothing reads once their output is made. Returns (deleted, bytes freed)."""
    in_paths = list(in_paths)
    random.shuffle(in_paths)
    n, freed = 0, 0
    for path in in_paths:
        out = out_path_of(path)
        if os.path.exists(out) and not os.path.exists(out + '.lock'):
            freed += os.path.getsize(path)
            os.remove(path)
            n += 1
    return n, freed
