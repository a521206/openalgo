# Gunicorn configuration for OpenAlgo
# Ensures the strategy scheduler is initialized in worker processes after forking

import logging
import os
import threading
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gunicorn.postfork")


def _scheduler_health_monitor():
    """Background thread that monitors scheduler health and restarts if dead"""
    while True:
        time.sleep(60)  # Check every minute
        try:
            import blueprints.python_strategy as ps
            if ps.SCHEDULER is None or not ps.SCHEDULER.running:
                logger.warning("Health monitor: scheduler down, restarting")
                ps.init_scheduler()
                # Re-schedule strategies after restart
                for sid, cfg in ps.STRATEGY_CONFIGS.items():
                    if cfg.get("is_scheduled") and cfg.get("schedule_start"):
                        try:
                            ps.schedule_strategy(
                                sid, cfg["schedule_start"], cfg.get("schedule_stop"), cfg.get("schedule_days")
                            )
                        except Exception as e:
                            logger.warning(f"Health monitor: failed to restore schedule for {sid}: {e}")
        except Exception as e:
            logger.error(f"Health monitor error: {e}")


def post_fork(server, worker):
    """Initialize scheduler after Gunicorn forks a worker"""
    logger.info(f"Worker {worker.pid} forked - initializing strategy scheduler")
    try:
        import blueprints.python_strategy as ps
        logger.info(f"Before init: SCHEDULER={ps.SCHEDULER}, running={getattr(ps.SCHEDULER, 'running', 'N/A')}")
        # Clear stale scheduler object from master process (dead thread after fork)
        ps.SCHEDULER = None
        ps.init_scheduler()
        logger.info(f"After init: SCHEDULER={ps.SCHEDULER}, running={getattr(ps.SCHEDULER, 'running', 'N/A')}")
        # Start background health monitor thread
        monitor = threading.Thread(target=_scheduler_health_monitor, daemon=True, name="scheduler-monitor")
        monitor.start()
        logger.info(f"Strategy scheduler initialized in worker {worker.pid}")
    except Exception as e:
        logger.error(f"Failed to initialize scheduler in worker {worker.pid}: {e}", exc_info=True)
