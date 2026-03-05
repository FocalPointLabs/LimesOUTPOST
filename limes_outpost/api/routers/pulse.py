"""
limes_outpost.api.routers.pulse
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
GET  /ventures/{id}/pulse/latest
POST /ventures/{id}/pulse/run      — trigger on-demand pulse
"""

from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from limes_outpost.api.dependencies import DBPool, AnyMember

router = APIRouter()


@router.get("/latest")
async def get_latest_pulse(venture_id: str, venture: AnyMember, db_pool: DBPool):
    """Returns the most recent pulse report for this venture."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, venture_id, stats, briefing, created_at
                FROM public.pulse_reports
                WHERE venture_id = %s
                ORDER BY created_at DESC
                LIMIT 1;
            """, (venture_id,))
            row = cur.fetchone()
    finally:
        db_pool.putconn(conn)

    if not row:
        return {"report": None}

    return {
        "report": {
            "id":         str(row[0]),
            "venture_id": row[1],
            "stats":      row[2],
            "briefing":   row[3],
            "created_at": row[4].isoformat(),
        }
    }


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def trigger_pulse(
    venture_id: str,
    venture: AnyMember,
    background_tasks: BackgroundTasks,
):
    """Triggers an on-demand pulse report via Celery."""
    try:
        from limes_outpost.tasks.pipeline_tasks import run_pulse
        task = run_pulse.delay(venture_id=venture_id)
        return {"task_id": task.id, "status": "queued"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
