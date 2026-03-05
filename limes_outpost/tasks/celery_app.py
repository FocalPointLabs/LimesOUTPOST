"""
limes_outpost.tasks.celery_app
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Celery application factory and Beat dynamic schedule loader.

Beat reads workflow_schedule from every active venture in the DB on
startup and registers one task per enabled workflow per venture.
When a venture's schedule changes via API (Phase 4), Beat picks it up
on the next tick — no restart required.

Priority queues
---------------
high    — publish actions, queue approve/reject, auth operations
default — pipeline runs, email/social cycles
low     — analytics pulls, pulse reports, beat-scheduled background runs
"""

import os
import json
import logging
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("limes_outpost.celery")

# ─────────────────────────────────────────────────────────────
#  App factory
# ─────────────────────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "limes_outpost",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "limes_outpost.tasks.pipeline_tasks",
        "limes_outpost.tasks.email_tasks",
        "limes_outpost.tasks.social_tasks",
    ],
)

app.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Reliability
    task_acks_late=True,               # ack only after task completes
    task_reject_on_worker_lost=True,   # requeue if worker dies mid-task
    worker_prefetch_multiplier=1,      # one task at a time per worker slot

    # Result TTL — we track progress in Postgres, not the result backend
    result_expires=3600,

    # Priority queue routing
    task_default_queue="default",
    task_queues={
        "high":    {"exchange": "high",    "routing_key": "high"},
        "default": {"exchange": "default", "routing_key": "default"},
        "low":     {"exchange": "low",     "routing_key": "low"},
    },
    task_routes={
        "limes_outpost.tasks.pipeline_tasks.run_scheduler":        {"queue": "high"},
        "limes_outpost.tasks.pipeline_tasks.run_pipeline":         {"queue": "default"},
        "limes_outpost.tasks.email_tasks.run_email_cycle":         {"queue": "default"},
        "limes_outpost.tasks.social_tasks.run_social_reply_cycle": {"queue": "default"},
        "limes_outpost.tasks.pipeline_tasks.run_pulse":            {"queue": "low"},
        "limes_outpost.tasks.pipeline_tasks.pull_analytics":       {"queue": "low"},
    },
)


# ─────────────────────────────────────────────────────────────
#  Beat dynamic schedule
# ─────────────────────────────────────────────────────────────

# Workflow name → Celery task path
WORKFLOW_TASK_MAP = {
    "short_form_video": "limes_outpost.tasks.pipeline_tasks.run_pipeline",
    "blog_post":        "limes_outpost.tasks.pipeline_tasks.run_pipeline",
    "email":            "limes_outpost.tasks.email_tasks.run_email_cycle",
    "social_reply":     "limes_outpost.tasks.social_tasks.run_social_reply_cycle",
    "analytics":        "limes_outpost.tasks.pipeline_tasks.pull_analytics",
    "publish":          "limes_outpost.tasks.pipeline_tasks.run_scheduler",  # ADD THIS
}

def _parse_cron(cron_str: str) -> crontab:
    """
    Parses a 5-field cron string into a Celery crontab.
    '0 9 * * *'  →  crontab(minute='0', hour='9')
    Raises ValueError on malformed input.
    """
    parts = cron_str.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (need 5 fields): '{cron_str}'")
    minute, hour, day_of_month, month_of_year, day_of_week = parts
    return crontab(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
    )


def load_venture_schedules() -> dict:
    """
    Reads workflow_schedule from all active ventures in the DB.
    Returns a Celery beat_schedule dict ready to assign to app.conf.

    Called once at Beat startup. Beat re-reads on each tick if
    app.conf.beat_schedule is reassigned (see worker/main.py).

    Fails gracefully — if the DB is unreachable, returns an empty
    schedule so Beat starts without crashing. Logs a warning.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "limes_outpost_db"),
            user=os.getenv("DB_USER", "limes_outpost_user"),
            password=os.getenv("DB_PASSWORD", "limes_outpost_password"),
            port=int(os.getenv("DB_PORT", "5432")),
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT id, timezone, workflow_schedule
            FROM public.ventures
            WHERE status = 'active'
              AND workflow_schedule IS NOT NULL
              AND workflow_schedule != '{}'::jsonb;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

    except Exception as e:
        print(f"[Beat] Could not load venture schedules from DB: {e}")
        logger.warning(f"[Beat] Could not load venture schedules from DB: {e}")
        return {}

    schedule = {}

    for venture_id, tz, raw_schedule in rows:
        if isinstance(raw_schedule, str):
            try:
                raw_schedule = json.loads(raw_schedule)
            except json.JSONDecodeError:
                logger.warning(f"[Beat] Malformed workflow_schedule for venture {venture_id}")
                continue

        for workflow_name, config in raw_schedule.items():
            if not isinstance(config, dict):
                continue
            if not config.get("enabled", False):
                continue

            cron_str = config.get("cron")
            task_path = WORKFLOW_TASK_MAP.get(workflow_name)

            if not cron_str or not task_path:
                logger.warning(
                    f"[Beat] Skipping {venture_id}/{workflow_name} — "
                    f"missing cron or unknown workflow"
                )
                continue

            try:
                schedule_key = f"{venture_id}__{workflow_name}"
                schedule[schedule_key] = {
                    "task": task_path,
                    "schedule": _parse_cron(cron_str),
                    "args": [venture_id],
                    "kwargs": {"workflow": workflow_name},
                    "options": {"queue": "low"},
                }
                print(f"[Beat] Registered: {schedule_key} -> {cron_str}")
                logger.warning(f"[Beat] Registered: {schedule_key} -> {cron_str}")
            except ValueError as e:
                logger.warning(f"[Beat] Bad cron for {venture_id}/{workflow_name}: {e}")
                continue

    print(f"[Beat] Loaded {len(schedule)} scheduled task(s) from DB.")
    logger.warning(f"[Beat] Loaded {len(schedule)} scheduled task(s) from DB.")
    return schedule


# Load schedule at module import time (Beat reads this on startup)
app.conf.beat_schedule = load_venture_schedules()