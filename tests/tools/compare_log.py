from pathlib import Path

def contains_in_order(text: str, needles):
    """Return True if all needles appear in text in the given order."""
    idx = 0
    for n in needles:
        i = text.find(n, idx)
        if i == -1:
            return False
        idx = i + len(n)
    return True


def latest_log_for(job_id: str, log_dir: Path):
    files = list(log_dir.glob(f"dagrunner_*_{job_id}.log"))
    if not files:
        return None
    return sorted(files)[-1]
 