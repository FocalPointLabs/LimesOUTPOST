"""
limes_outpost.api.routers.publish
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
POST /ventures/{venture_id}/publish/all
POST /ventures/{venture_id}/publish/{platform}
POST /ventures/{venture_id}/email/run
POST /ventures/{venture_id}/social/run
"""

from fastapi import APIRouter, HTTPException, status

from limes_outpost.api.dependencies import DBPool, OperatorOnly
from limes_outpost.api.schemas import PublishTriggerRequest, PublishTriggerResponse

router = APIRouter()

SUPPORTED_PLATFORMS = {"youtube", "twitter", "email"}


# ─────────────────────────────────────────────────────────────
#  Trigger all platforms publish scheduler
# ─────────────────────────────────────────────────────────────

@router.post("/{venture_id}/publish/all", response_model=PublishTriggerResponse)
async def trigger_publish_all(venture_id: str, venture: OperatorOnly):
    """Publishes all approved items across all platforms."""
    from limes_outpost.tasks.pipeline_tasks import run_scheduler as _task
    task = _task.delay(venture_id=venture_id, platform=None)
    return PublishTriggerResponse(task_id=task.id, platform="all")


# ─────────────────────────────────────────────────────────────
#  Trigger platform publish scheduler
# ─────────────────────────────────────────────────────────────

@router.post("/{venture_id}/publish/{platform}", response_model=PublishTriggerResponse)
async def trigger_publish(
    venture_id: str,
    platform:   str,
    venture:    OperatorOnly,
):
    """
    Triggers the publish scheduler for a specific platform.
    Picks up all 'approved' items from publish_queue for that platform
    and dispatches them.
    """
    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform '{platform}'. Must be one of: {sorted(SUPPORTED_PLATFORMS)}.",
        )

    from limes_outpost.tasks.pipeline_tasks import run_scheduler as _task
    task = _task.delay(venture_id=venture_id, platform=platform)

    return PublishTriggerResponse(task_id=task.id, platform=platform)


# ─────────────────────────────────────────────────────────────
#  Trigger email cycle
# ─────────────────────────────────────────────────────────────

@router.post("/{venture_id}/email/run", response_model=PublishTriggerResponse)
async def trigger_email_cycle(venture_id: str, venture: OperatorOnly):
    """Enqueues a full email triage cycle (fetch → triage → draft → queue)."""
    from limes_outpost.tasks.email_tasks import run_email_cycle as _task
    task = _task.delay(venture_id=venture_id)
    return PublishTriggerResponse(task_id=task.id, platform="email")


# ─────────────────────────────────────────────────────────────
#  Trigger social reply cycle
# ─────────────────────────────────────────────────────────────

@router.post("/{venture_id}/social/run", response_model=PublishTriggerResponse)
async def trigger_social_cycle(venture_id: str, venture: OperatorOnly):
    """Enqueues a full social mention/reply cycle (fetch → triage → draft → queue)."""
    from limes_outpost.tasks.social_tasks import run_social_reply_cycle as _task
    task = _task.delay(venture_id=venture_id)
    return PublishTriggerResponse(task_id=task.id, platform="twitter")