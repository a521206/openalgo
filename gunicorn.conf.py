# Gunicorn configuration for OpenAlgo
# Ensures the strategy scheduler is initialized in worker processes after forking

def post_fork(server, worker):
    """Initialize scheduler after Gunicorn forks a worker"""
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("gunicorn.postfork")
    logger.info(f"Worker {worker.pid} forked - initializing strategy scheduler")
    try:
        import blueprints.python_strategy as ps
        logger.info(f"Before init: SCHEDULER={ps.SCHEDULER}, running={getattr(ps.SCHEDULER, 'running', 'N/A')}")
        # Clear stale scheduler object from master process (dead thread after fork)
        ps.SCHEDULER = None
        ps.init_scheduler()
        logger.info(f"After init: SCHEDULER={ps.SCHEDULER}, running={getattr(ps.SCHEDULER, 'running', 'N/A')}")
        logger.info(f"Strategy scheduler initialized in worker {worker.pid}")
    except Exception as e:
        logger.error(f"Failed to initialize scheduler in worker {worker.pid}: {e}", exc_info=True)
