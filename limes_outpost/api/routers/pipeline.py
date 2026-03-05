"""
limes_outpost.api.routers.pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
POST /ventures/{venture_id}/pipeline/run
GET  /ventures/{venture_id}/pipeline/{campaign_id}
WS   /ventures/{venture_id}/pipeline/{campaign_id}/ws
POST /ventures/{venture_id}/pulse
"""

import asyncio
import json
import logging

import psycopg2
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from limes_outpost.api.dependencies import DBPool, CurrentUser, AnyMember, OperatorOnly
from limes_outpost.api.schemas import (
    PipelineRunRequest, PipelineRunResponse,
    PipelineProgressResponse, PipelineStepResponse,
    PulseResponse,
)

router  = APIRouter()
logger  = logging.getLogger("limes_outpost.api.pipeline")


# ─────────────────────────────────────────────────────────────
#  Trigger pipeline run
# ─────────────────────────────────────────────────────────────

@router.post("/{venture_id}/pipeline/run", response_model=PipelineRunResponse)
async def run_pipeline(
    venture_id: str,
    body: PipelineRunRequest,
    venture: OperatorOnly,
    db_pool: DBPool,
):
    """
    Enqueues a pipeline run for the venture.
    Returns the Celery task_id immediately — poll /pipeline/{campaign_id}
    or open the WebSocket for live progress.
    """
    from limes_outpost.tasks.pipeline_tasks import run_pipeline as _task

    task = _task.delay(
        venture_id=venture_id,
        topic=body.topic,
        campaign_id=body.campaign_id,
    )

    return PipelineRunResponse(
        campaign_id=body.campaign_id,
        task_id=task.id,
    )


# ─────────────────────────────────────────────────────────────
#  Pipeline progress (polling endpoint)
# ─────────────────────────────────────────────────────────────


@router.get("/{venture_id}/pipeline/latest")
async def get_latest_campaign(
    venture_id: str,
    venture: AnyMember,
    db_pool: DBPool,
):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM public.campaigns WHERE venture_id = %s ORDER BY created_at DESC LIMIT 1;",
                (venture_id,)
            )
            row = cur.fetchone()
    finally:
        db_pool.putconn(conn)
    if not row:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=404, detail="No campaigns found.")
    return {"campaign_id": row[0]}


@router.get(
    "/{venture_id}/pipeline/{campaign_id}",
    response_model=PipelineProgressResponse,
)
async def get_pipeline_progress(
    venture_id:  str,
    campaign_id: int,
    venture: AnyMember,
    db_pool: DBPool,
):
    """
    Returns live pipeline progress by reading content_items from DB.
    The orchestrator writes status per step as it runs, so this reflects
    real-time state without needing the Celery result backend.
    """
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ci.id, ci.topic, ci.status, ci.created_at,
                       c.venture_id
                FROM public.content_items ci
                JOIN public.campaigns c ON c.id = ci.campaign_id
                WHERE ci.campaign_id = %s
                  AND c.venture_id   = %s
                ORDER BY ci.sequence_number;
            """, (campaign_id, venture_id))
            rows = cur.fetchall()
    finally:
        db_pool.putconn(conn)

    if not rows:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No pipeline data found for campaign {campaign_id}.",
        )

    steps = [
        PipelineStepResponse(
            step_id=r[0], topic=r[1], status=r[2], created_at=r[3]
        )
        for r in rows
    ]

    statuses = {s.status for s in steps}
    if "failed"    in statuses: overall = "failed"
    elif "processing" in statuses: overall = "running"
    elif all(s.status == "completed" for s in steps): overall = "completed"
    else: overall = "pending"

    return PipelineProgressResponse(
        campaign_id=campaign_id,
        venture_id=venture_id,
        steps=steps,
        overall=overall,
    )


# ─────────────────────────────────────────────────────────────
#  WebSocket — live pipeline progress
# ─────────────────────────────────────────────────────────────

@router.websocket("/{venture_id}/pipeline/{campaign_id}/ws")
async def pipeline_ws(
    websocket:   WebSocket,
    venture_id:  str,
    campaign_id: int,
    db_pool:     DBPool,
):
    """
    Streams pipeline step updates to the client in real time.

    Uses Postgres LISTEN/NOTIFY (no Redis needed for this):
      - The orchestrator fires NOTIFY pipeline_progress after each step.
      - This handler wakes up, reads current content_items state, and
        pushes a JSON snapshot to the connected client.

    Falls back to polling every 3 seconds if NOTIFY isn't wired yet
    (safe during development before the orchestrator is updated).
    """
    await websocket.accept()
    logger.info(f"[WS] Client connected: venture={venture_id} campaign={campaign_id}")

    # Dedicated connection for LISTEN (must not be returned to pool mid-listen)
    listen_conn = psycopg2.connect(
        host=__import__("os").getenv("DB_HOST", "localhost"),
        database=__import__("os").getenv("DB_NAME", "limes_outpost_db"),
        user=__import__("os").getenv("DB_USER", "limes_outpost_user"),
        password=__import__("os").getenv("DB_PASSWORD", "limes_outpost_password"),
        port=int(__import__("os").getenv("DB_PORT", "5432")),
    )
    listen_conn.set_isolation_level(0)  # AUTOCOMMIT required for LISTEN

    try:
        with listen_conn.cursor() as cur:
            cur.execute("LISTEN pipeline_progress;")

        last_snapshot = None

        while True:
            # Check for Postgres notification (non-blocking)
            listen_conn.poll()
            notified = bool(listen_conn.notifies)
            if notified:
                listen_conn.notifies.clear()

            # Also push on first connect and every 3s as fallback
            snapshot = await _fetch_progress_snapshot(db_pool, venture_id, campaign_id)

            if snapshot != last_snapshot or notified:
                await websocket.send_json(snapshot)
                last_snapshot = snapshot

            # Done — close WebSocket cleanly
            if snapshot.get("overall") in ("completed", "failed"):
                await websocket.close()
                break

            await asyncio.sleep(3)

    except WebSocketDisconnect:
        logger.info(f"[WS] Client disconnected: venture={venture_id} campaign={campaign_id}")
    finally:
        listen_conn.close()


async def _fetch_progress_snapshot(db_pool, venture_id: str, campaign_id: int) -> dict:
    """Reads current content_items state and returns a JSON-serialisable dict."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ci.id, ci.topic, ci.status, ci.created_at::text
                FROM public.content_items ci
                JOIN public.campaigns c ON c.id = ci.campaign_id
                WHERE ci.campaign_id = %s AND c.venture_id = %s
                ORDER BY ci.sequence_number;
            """, (campaign_id, venture_id))
            rows = cur.fetchall()
    finally:
        db_pool.putconn(conn)

    steps = [
        {"step_id": r[0], "topic": r[1], "status": r[2], "created_at": r[3]}
        for r in rows
    ]

    statuses = {s["status"] for s in steps}
    if "failed"       in statuses: overall = "failed"
    elif "processing" in statuses: overall = "running"
    elif steps and all(s["status"] == "completed" for s in steps): overall = "completed"
    else: overall = "pending"

    return {
        "campaign_id": campaign_id,
        "venture_id":  venture_id,
        "steps":       steps,
        "overall":     overall,
    }


# ─────────────────────────────────────────────────────────────
#  Pulse
# ─────────────────────────────────────────────────────────────

@router.post("/{venture_id}/pulse", response_model=PulseResponse)
async def trigger_pulse(venture_id: str, venture: AnyMember):
    """Enqueues a pulse report generation task."""
    from limes_outpost.tasks.pipeline_tasks import run_pulse as _task
    task = _task.delay(venture_id=venture_id)
    return PulseResponse(venture_id=venture_id, task_id=task.id)





@router.get("/{venture_id}/pipeline")
async def list_campaigns(
    venture_id: str,
    venture: AnyMember,
    db_pool: DBPool,
):
    """Returns all campaigns for a venture, most recent first."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    c.id,
                    c.status,
                    c.created_at::text,
                    COUNT(ci.id) as total_steps,
                    SUM(CASE WHEN ci.status = 'completed' THEN 1 ELSE 0 END) as completed_steps,
                    SUM(CASE WHEN ci.status = 'failed' THEN 1 ELSE 0 END) as failed_steps,
                    SUM(CASE WHEN ci.status = 'processing' THEN 1 ELSE 0 END) as processing_steps
                FROM public.campaigns c
                LEFT JOIN public.content_items ci ON ci.campaign_id = c.id
                WHERE c.venture_id = %s
                GROUP BY c.id, c.status, c.created_at
                ORDER BY c.created_at DESC
                LIMIT 50;
            """, (venture_id,))
            rows = cur.fetchall()
    finally:
        db_pool.putconn(conn)

    return [
        {
            "campaign_id":       r[0],
            "status":            r[1],
            "created_at":        r[2],
            "total_steps":       r[3],
            "completed_steps":   r[4],
            "failed_steps":      r[5],
            "processing_steps":  r[6],
        }
        for r in rows
    ]
