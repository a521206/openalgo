# gunicorn.conf.py
# Gunicorn configuration for OpenAlgo
# NOTE: Scheduler is now a standalone process (scheduler.py)
# No scheduler initialization in the Flask worker

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gunicorn.postfork")


def post_fork(server, worker):
    """Post-fork hook — worker is ready"""
    logger.info(f"Worker {worker.pid} forked and ready")
