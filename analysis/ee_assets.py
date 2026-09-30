"""Earth Engine asset and export-task helpers shared by the pipeline stages."""

import logging
import time

import ee

log = logging.getLogger(__name__)
TASK_POLL_INTERVAL_S = 30


def ensure_folder(path: str) -> None:
    try:
        ee.data.getAsset(path)
    except ee.EEException:
        ee.data.createFolder(path)


def asset_exists(path: str) -> bool:
    try:
        ee.data.getAsset(path)
        return True
    except ee.EEException:
        return False


def wait_for_tasks(tasks: list) -> None:
    """tasks: (label, ee.batch.Task) pairs. Blocks until all complete; raises on failure."""
    pending = dict(tasks)
    while pending:
        for label, task in list(pending.items()):
            status = task.status()
            state = status["state"]
            if state == "COMPLETED":
                log.info("%s: export complete", label)
                del pending[label]
            elif state in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"Export {label} {state}: {status.get('error_message')}")
        if pending:
            time.sleep(TASK_POLL_INTERVAL_S)
