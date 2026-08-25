# Gunicorn configuration for OpenAlgo
# Ensures the strategy scheduler is initialized in worker processes after forking

def post_fork(server, worker):
    """Initialize scheduler after Gunicorn forks a worker"""
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("gunicorn.postfork")
    logger.info(f"Worker {worker.pid} forked - initializing strategy scheduler")
    try:
        from blueprints.python_strategy import init_scheduler, SCHEDULER
        # Clear stale scheduler object from master process (dead thread after fork)
        import blueprints.python_strategy as ps
        ps.SCHEDULER = None
        init_scheduler()
        logger.info(f"Strategy scheduler initialized in worker {worker.pid}")
    except Exception as e:
        logger.error(f"Failed to initialize scheduler in worker {worker.pid}: {e}")
