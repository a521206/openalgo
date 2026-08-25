#!/usr/bin/env python
"""
OpenAlgo Standalone Strategy Scheduler
=======================================
Runs APScheduler as a separate process, independent of Flask/Gunicorn.
Communicates with Flask via shared SQLite database and strategy_configs.json.

This process:
  - Reads strategy schedules from the database
  - Triggers start/stop via cron triggers
  - Manages strategy subprocess lifecycle
  - Survives Flask restarts and Gunicorn worker recycling

Managed by systemd as a separate service (openalgo-scheduler-*.service).
"""
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IST = pytz.timezone("Asia/Kolkata")
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "strategies" / "strategy_configs.json"
LOGS_DIR = BASE_DIR / "log" / "strategies"
STRATEGIES_DIR = BASE_DIR / "strategies" / "scripts"
RUNNING_FILE = BASE_DIR / "strategies" / "running_strategies.json"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s in %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "log" / "scheduler.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("scheduler")

# Graceful shutdown flag
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum}, shutting down...")
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def load_json(path: Path, default=None):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default or {}


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False))
    tmp.replace(path)


def get_running() -> dict:
    return load_json(RUNNING_FILE, {})


def save_running(data: dict):
    save_json(RUNNING_FILE, data)


# ---------------------------------------------------------------------------
# Strategy lifecycle
# ---------------------------------------------------------------------------
def start_strategy(strategy_id: str):
    """Launch a strategy subprocess and record its PID."""
    configs = load_json(CONFIG_FILE, {})
    config = configs.get(strategy_id)
    if not config:
        logger.warning(f"Strategy {strategy_id} not found in configs")
        return

    file_path = Path(config.get("file_path", ""))
    if not file_path.exists():
        logger.error(f"Strategy file not found: {file_path}")
        return

    ist_now = datetime.now(IST)
    log_file = LOGS_DIR / f"{strategy_id}_{ist_now:%Y%m%d_%H%M%S}_IST.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with open(log_file, "w", encoding="utf-8") as lf:
            proc = subprocess.Popen(
                [sys.executable, "-u", str(file_path)],
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=str(BASE_DIR),
            )
    except Exception as e:
        logger.error(f"Failed to start {strategy_id}: {e}")
        return

    running = get_running()
    running[strategy_id] = {
        "pid": proc.pid,
        "started_at": str(ist_now),
        "log_file": str(log_file),
    }
    save_running(running)

    configs[strategy_id]["is_running"] = True
    configs[strategy_id]["pid"] = proc.pid
    configs[strategy_id]["last_started"] = ist_now.isoformat()
    save_json(CONFIG_FILE, configs)

    logger.info(f"Started strategy {strategy_id} (PID {proc.pid})")


def stop_strategy(strategy_id: str):
    """Terminate a running strategy subprocess."""
    running = get_running()
    info = running.get(strategy_id)
    if not info:
        return

    pid = info.get("pid")
    if pid:
        try:
            proc = psutil.Process(pid)
            for child in proc.children(recursive=True):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            proc.terminate()
            gone, alive = psutil.wait_procs([proc] + proc.children(recursive=True), timeout=5)
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            logger.warning(f"Error stopping {strategy_id}: {e}")

    running.pop(strategy_id, None)
    save_running(running)

    configs = load_json(CONFIG_FILE, {})
    if strategy_id in configs:
        configs[strategy_id]["is_running"] = False
        configs[strategy_id]["pid"] = None
        configs[strategy_id]["last_stopped"] = datetime.now(IST).isoformat()
        save_json(CONFIG_FILE, configs)

    logger.info(f"Stopped strategy {strategy_id}")


# ---------------------------------------------------------------------------
# Job synchronisation
# ---------------------------------------------------------------------------
def sync_jobs(scheduler: BlockingScheduler):
    """Read strategy configs and synchronise APScheduler cron jobs."""
    configs = load_json(CONFIG_FILE, {})

    # Remove all existing strategy jobs
    for job in scheduler.get_jobs():
        if job.id.startswith(("start_", "stop_")):
            scheduler.remove_job(job.id)

    for strategy_id, config in configs.items():
        if not config.get("is_scheduled"):
            continue

        start_time = config.get("schedule_start", "09:00")
        stop_time = config.get("schedule_stop", "16:00")
        days = config.get("schedule_days", ["mon", "tue", "wed", "thu", "fri"])

        # Start job
        try:
            sh, sm = map(int, start_time.split(":"))
            scheduler.add_job(
                lambda sid=strategy_id: start_strategy(sid),
                CronTrigger(hour=sh, minute=sm, day_of_week=",".join(days), timezone=IST),
                id=f"start_{strategy_id}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        except Exception as e:
            logger.error(f"Failed to schedule start {strategy_id}: {e}")

        # Stop job
        if stop_time:
            try:
                eh, em = map(int, stop_time.split(":"))
                scheduler.add_job(
                    lambda sid=strategy_id: stop_strategy(sid),
                    CronTrigger(hour=eh, minute=em, day_of_week=",".join(days), timezone=IST),
                    id=f"stop_{strategy_id}",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )
            except Exception as e:
                logger.error(f"Failed to schedule stop {strategy_id}: {e}")

    logger.debug(f"Synced {sum(1 for _ in scheduler.get_jobs())} scheduler jobs")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    logger.info("=" * 60)
    logger.info("OpenAlgo Strategy Scheduler starting")
    logger.info(f"Config: {CONFIG_FILE}")
    logger.info(f"Strategies dir: {STRATEGIES_DIR}")
    logger.info("=" * 60)

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)

    scheduler = BlockingScheduler(timezone=IST)

    # Initial sync
    sync_jobs(scheduler)

    # Periodic re-sync (every 30s) to pick up config changes from Flask
    scheduler.add_job(sync_jobs, "interval", seconds=30, args=[scheduler], id="sync_jobs")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        logger.info("Scheduler shut down")


if __name__ == "__main__":
    main()
