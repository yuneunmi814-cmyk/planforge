"""Queue-consuming worker process.

Run with:  python -m app.worker.worker
Consumes generation job ids from Redis and processes them. Scale by running N
copies. The loop never crashes on a single bad job (design: 비관적 기본값)."""

import logging

from app.core.database import Base, SessionLocal, engine
from app.services.queue import get_queue
from app.worker.processor import process_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker: %(message)s")
log = logging.getLogger(__name__)


def run() -> None:
    Base.metadata.create_all(bind=engine)
    queue = get_queue()
    log.info("planforge worker started, waiting for jobs…")
    while True:
        payload = queue.dequeue(timeout=5)
        if not payload:
            continue
        job_id = payload.get("jobId")
        if job_id is None:
            log.warning("invalid payload: %s", payload)
            continue
        with SessionLocal() as db:
            try:
                status = process_job(db, job_id)
                log.info("job %s -> %s", job_id, status)
            except Exception:  # noqa: BLE001 — worker must never crash the loop
                log.exception("job %s failed unexpectedly", job_id)


if __name__ == "__main__":
    run()
