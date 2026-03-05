"""
limes_outpost.tasks.email_tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Email cycle Celery tasks.
"""

import logging
from limes_outpost.tasks.celery_app import app
from limes_outpost.tasks.pipeline_tasks import LimesOutpostTask

logger = logging.getLogger("limes_outpost.tasks.email")


@app.task(
    base=LimesOutpostTask,
    bind=True,
    queue="default",
    max_retries=2,
    default_retry_delay=30,
    name="limes_outpost.tasks.email_tasks.run_email_cycle",
)
def run_email_cycle(self, venture_id: str, workflow: str = None):
    """
    Runs the full email triage cycle for a venture:
    fetch → triage → draft → queue.

    Equivalent to: python cli/main.py --email <venture_id>

    Args:
        venture_id: The venture to run the email cycle for.
        workflow:   Unused — accepted for Beat schedule compatibility.
    """
    from limes_outpost.agents.inbox_agent import InboxAgent
    from limes_outpost.agents.triage_agent import TriageAgent
    from limes_outpost.agents.draft_agent import DraftAgent
    from limes_outpost.agents.orchestrator import LimesOutpostOrchestrator

    logger.info(f"[run_email_cycle] Starting | venture={venture_id}")

    try:
        factory        = LimesOutpostOrchestrator(venture_id=venture_id)
        brand_snapshot = factory.brand_snapshot
        services       = {"db_pool": factory.db_pool}

        # 1. Fetch
        inbox   = InboxAgent(services=services)
        result  = inbox.run(input_data={}, context=brand_snapshot)
        fetched = result.get("fetched", 0)
        logger.info(f"[run_email_cycle] Fetched {fetched} thread(s).")

        if fetched == 0 and result.get("skipped", 0) == 0:
            logger.info(f"[run_email_cycle] No new threads fetched — checking for untriaged existing threads.")

        # 2. Triage
        triage = TriageAgent(services=services)
        result = triage.run(input_data={}, context=brand_snapshot)
        logger.info(
            f"[run_email_cycle] Triaged: {result.get('triaged', 0)} | "
            f"Ignored: {result.get('ignored', 0)}"
        )

        # 3. Draft
        draft   = DraftAgent(services=services)
        result  = draft.run(input_data={}, context=brand_snapshot)
        drafted = result.get("drafted", 0)
        logger.info(f"[run_email_cycle] Drafted {drafted} reply/replies.")

        return {
            "status":     "success",
            "venture_id": venture_id,
            "fetched":    fetched,
            "drafted":    drafted,
        }

    except Exception as exc:
        logger.error(f"[run_email_cycle] Error for venture {venture_id}: {exc}")
        raise self.retry(exc=exc)
