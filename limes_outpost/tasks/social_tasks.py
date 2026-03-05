"""
limes_outpost.tasks.social_tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Social reply cycle Celery tasks.
"""

import logging
from limes_outpost.tasks.celery_app import app
from limes_outpost.tasks.pipeline_tasks import LimesOutpostTask

logger = logging.getLogger("limes_outpost.tasks.social")


@app.task(
    base=LimesOutpostTask,
    bind=True,
    queue="default",
    max_retries=2,
    default_retry_delay=30,
    name="limes_outpost.tasks.social_tasks.run_social_reply_cycle",
)
def run_social_reply_cycle(self, venture_id: str, workflow: str = None):
    """
    Runs the social mention/reply cycle for a venture:
    fetch mentions → triage (inline in MentionAgent) → draft replies → queue.

    Args:
        venture_id: The venture to run the social cycle for.
        workflow:   Unused — accepted for Beat schedule compatibility.
    """
    from limes_outpost.agents.mention_agent import MentionAgent
    from limes_outpost.agents.reply_agent import ReplyAgent
    from limes_outpost.agents.orchestrator import LimesOutpostOrchestrator

    logger.info(f"[run_social_reply_cycle] Starting | venture={venture_id}")

    try:
        factory        = LimesOutpostOrchestrator(venture_id=venture_id)
        brand_snapshot = factory.brand_snapshot
        services       = {"db_pool": factory.db_pool}

        # 1. Fetch + triage mentions (triage is inline in MentionAgent)
        mention = MentionAgent(services=services)
        result  = mention.run(input_data={}, context=brand_snapshot)
        fetched = result.get("fetched", 0)
        triaged = result.get("triaged", 0)
        logger.info(f"[run_social_reply_cycle] Fetched {fetched} | Triaged {triaged}")

        # 2. Draft replies for all triaged mentions (including from prior runs)
        reply   = ReplyAgent(services=services)
        result  = reply.run(input_data={}, context=brand_snapshot)
        drafted = result.get("drafted", 0)
        logger.info(f"[run_social_reply_cycle] Drafted {drafted} reply/replies.")

        return {
            "status":     "success",
            "venture_id": venture_id,
            "fetched":    fetched,
            "triaged":    triaged,
            "drafted":    drafted,
        }

    except Exception as exc:
        logger.error(f"[run_social_reply_cycle] Error for venture {venture_id}: {exc}")
        raise self.retry(exc=exc)