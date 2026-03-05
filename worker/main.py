"""
worker/main.py
~~~~~~~~~~~~~~
Celery + Beat entry point. Imports the app so Celery can discover it.

Worker:
    celery -A worker.main worker --loglevel=info --queues=high,default,low

Beat:
    celery -A worker.main beat --loglevel=info --scheduler=celery.beat.PersistentScheduler

Both commands are defined in docker-compose.yml and run as separate containers.
"""

from limes_outpost.tasks.celery_app import app  # noqa: F401 — Celery discovers tasks via app.include
