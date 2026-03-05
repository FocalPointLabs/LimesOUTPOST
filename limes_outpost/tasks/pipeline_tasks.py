"""
limes_outpost.tasks.pipeline_tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Content pipeline Celery tasks.

Each task is a thin wrapper around the existing agent/orchestrator logic —
the same code that runs via CLI now runs asynchronously via Celery.

Progress tracking
-----------------
We do NOT use the Celery result backend for progress. The orchestrator
already writes status to content_items rows as each step completes.
The API (Phase 4) polls /pipeline/{campaign_id} which reads live from DB.
"""

import logging
import time
from celery import Task
from limes_outpost.tasks.celery_app import app
from limes_outpost.integrations.discord import OutpostSignalClient
from limes_outpost.integrations.channel_adapter import LimesOutpostAdapter

logger = logging.getLogger("limes_outpost.tasks.pipeline")


# ─────────────────────────────────────────────────────────────
#  Base task class — shared retry/error behaviour
# ─────────────────────────────────────────────────────────────

class LimesOutpostTask(Task):
    """
    Base class for all LimesOutpost tasks.
    Logs task start/success/failure consistently.
    Subclass and set abstract = True so Celery doesn't register it directly.
    """
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            f"[{self.name}] FAILED | task_id={task_id} | "
            f"args={args} kwargs={kwargs} | error={exc}"
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(
            f"[{self.name}] RETRYING | task_id={task_id} | error={exc}"
        )

    def on_success(self, retval, task_id, args, kwargs):
        logger.info(
            f"[{self.name}] SUCCESS | task_id={task_id}"
        )


# ─────────────────────────────────────────────────────────────
#  run_pipeline
# ─────────────────────────────────────────────────────────────

@app.task(
    base=LimesOutpostTask,
    bind=True,
    queue="default",
    max_retries=2,
    default_retry_delay=30,
    name="limes_outpost.tasks.pipeline_tasks.run_pipeline",
)
def run_pipeline(self, venture_id: str, topic: str = None, campaign_id: int = None, workflow: str = None):
    """
    Runs the full intelligence-to-production pipeline for a venture.

    Equivalent to: python cli/main.py <venture_id> [topic]

    Args:
        venture_id:  The venture to run for.
        topic:       Optional manual topic override.
        campaign_id: Optional — resume an existing campaign.
        workflow:    Optional — restrict to a specific workflow
                     (e.g. 'short_form_video', 'blog_post').
                     None = run all enabled workflows.

    Returns:
        dict with campaign_id and per-workflow output summary.
    """
    from limes_outpost.agents.intel_agent import IntelAgent
    from limes_outpost.agents.orchestrator import LimesOutpostOrchestrator

    logger.info(f"[run_pipeline] Starting | venture={venture_id} topic={topic} campaign={campaign_id}")
    start = time.time()

    try:
        factory        = LimesOutpostOrchestrator(venture_id=venture_id)
        brand_snapshot = factory.brand_snapshot
        services       = {"db_pool": factory.db_pool}

        # Intel scout phase
        scout_input = {"manual_query": topic} if topic else {}
        scout = IntelAgent(services=services)
        scout.run(input_data=scout_input, context=brand_snapshot)

        # Production pipeline
        initial_input = {"manual_query": topic} if topic else {}
        result = factory.run_production_pipeline(
            initial_input=initial_input,
            campaign_id=campaign_id,
        )

        # Fire and Forget Signal
        try:
            elapsed = round(time.time() - start)
            signal = OutpostSignalClient()
            adapter = LimesOutpostAdapter(signal)
            adapter.broadcast_complete(venture_id, campaign_id, result, elapsed)
        except Exception as e:
            logger.error(f"[run_pipeline] Signal broadcast failed: {e}")

        return {
            "status":      "success",
            "venture_id":  venture_id,
            "campaign_id": campaign_id,
            "result":      result,
        }

    except Exception as exc:
        logger.error(f"[run_pipeline] Error for venture {venture_id}: {exc}")
        
        # Trigger Violation Signal
        try:
            signal = OutpostSignalClient()
            adapter = LimesOutpostAdapter(signal)
            adapter.broadcast_violation(venture_id, "pipeline_core", str(exc))
        except Exception as e:
            logger.error(f"[run_pipeline] Violation signal failed: {e}")
            
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────
#  run_scheduler
# ─────────────────────────────────────────────────────────────

@app.task(
    base=LimesOutpostTask,
    bind=True,
    queue="high",
    max_retries=3,
    default_retry_delay=15,
    name="limes_outpost.tasks.pipeline_tasks.run_scheduler",
)
def run_scheduler(self, venture_id: str, platform: str = None, workflow: str = None):
    """
    Publishes approved items from publish_queue for a venture.

    Equivalent to: python cli/main.py --scheduler <venture_id>

    Args:
        venture_id: The venture to publish for.
        platform:   Platform filter ('youtube', 'twitter', 'email', 'blog').
                    None = all platforms.
        workflow:   Passed by Beat schedule — ignored (platform=None covers all).
    """
    from limes_outpost.agents.publish_scheduler import PublishScheduler
    from limes_outpost.agents.orchestrator import LimesOutpostOrchestrator

    # When triggered by Beat via WORKFLOW_TASK_MAP, workflow='publish' is passed.
    # We always want to process all platforms in that case.
    if workflow == "publish":
        platform = None

    logger.info(f"[run_scheduler] Starting | venture={venture_id} platform={platform or 'all'}")

    try:
        factory   = LimesOutpostOrchestrator(venture_id=venture_id)
        scheduler = PublishScheduler(db_pool=factory.db_pool)
        result    = scheduler.run(platform=platform)
        return {"status": "success", "venture_id": venture_id, "result": result}

    except Exception as exc:
        logger.error(f"[run_scheduler] Error for venture {venture_id}: {exc}")
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────
#  run_pulse
# ─────────────────────────────────────────────────────────────

@app.task(
    base=LimesOutpostTask,
    bind=True,
    queue="low",
    max_retries=1,
    name="limes_outpost.tasks.pipeline_tasks.run_pulse",
)
def run_pulse(self, venture_id: str):
    """
    Generates the daily pulse report for a venture.

    Equivalent to: python cli/main.py --pulse <venture_id>
    """
    from limes_outpost.agents.pulse_agent import PulseAgent
    from limes_outpost.agents.orchestrator import LimesOutpostOrchestrator

    logger.info(f"[run_pulse] Starting | venture={venture_id}")

    try:
        factory = LimesOutpostOrchestrator(venture_id=venture_id)
        pulse   = PulseAgent(services={"db_pool": factory.db_pool})
        result  = pulse.run(input_data={}, context=factory.brand_snapshot)
        return {"status": "success", "venture_id": venture_id, "result": result}

    except Exception as exc:
        logger.error(f"[run_pulse] Error for venture {venture_id}: {exc}")
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────
#  pull_analytics
# ─────────────────────────────────────────────────────────────

@app.task(
    base=LimesOutpostTask,
    bind=True,
    queue="low",
    max_retries=2,
    default_retry_delay=60,
    name="limes_outpost.tasks.pipeline_tasks.pull_analytics",
)
def pull_analytics(self, venture_id: str, platform: str = "youtube"):
    """
    Pulls platform analytics for all published assets for a venture
    and writes rows to analytics_events.

    Scheduled daily via Beat (low priority queue).

    Args:
        venture_id: The venture to pull analytics for.
        platform:   Platform to pull from. Defaults to 'youtube'.
    """
    logger.info(f"[pull_analytics] Starting | venture={venture_id} platform={platform}")

    if platform != "youtube":
        logger.info(f"[pull_analytics] Platform '{platform}' not yet supported (Phase 5 covers YouTube only).")
        return {"status": "skipped", "venture_id": venture_id, "platform": platform}

    try:
        from limes_outpost.agents.youtube_analytics_agent import YouTubeAnalyticsAgent
        from limes_outpost.agents.orchestrator import LimesOutpostOrchestrator

        factory = LimesOutpostOrchestrator(venture_id=venture_id)
        agent   = YouTubeAnalyticsAgent(services={"db_pool": factory.db_pool})
        result  = agent.run(input_data={}, context=factory.brand_snapshot)

        return result

    except Exception as exc:
        logger.error(f"[pull_analytics] Error for venture {venture_id}: {exc}")
        raise self.retry(exc=exc)