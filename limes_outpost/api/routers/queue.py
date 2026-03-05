"""
limes_outpost.api.routers.queue
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
GET   /ventures/{venture_id}/queue
PATCH /ventures/{venture_id}/queue/{item_id}
"""

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, status

from limes_outpost.api.dependencies import DBPool, AnyMember, OperatorOnly
from limes_outpost.api.schemas import QueueItemResponse, QueuePatchRequest

router = APIRouter()


# ─────────────────────────────────────────────────────────────
#  List queue
# ─────────────────────────────────────────────────────────────

@router.get("/{venture_id}/queue", response_model=list[QueueItemResponse])
async def list_queue(
    venture_id: str,
    venture:    AnyMember,
    db_pool:    DBPool,
    platform:   Optional[str] = None,
    status_filter: Optional[str] = "pending_review",
):
    """
    Returns publish queue items for the venture.

    Query params:
        platform      — filter by platform (youtube, twitter, email)
        status_filter — defaults to 'pending_review'; pass 'all' for everything
    """
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT pq.id, pq.venture_id, pq.platform, pq.status,
                       pq.title, pq.description, pq.tags,
                       pq.created_at, pq.scheduled_for
                FROM public.publish_queue pq
                WHERE pq.venture_id = %s
            """
            params = [venture_id]

            if platform:
                query += " AND pq.platform = %s"
                params.append(platform)

            if status_filter and status_filter != "all":
                query += " AND pq.status = %s"
                params.append(status_filter)

            query += " ORDER BY pq.created_at DESC;"
            cur.execute(query, params)
            rows = cur.fetchall()
    finally:
        db_pool.putconn(conn)

    return [
        QueueItemResponse(
            id=r[0], venture_id=r[1], platform=r[2], status=r[3],
            title=r[4], description=r[5], tags=r[6],
            created_at=r[7], scheduled_for=r[8],
        )
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────
#  Review action — approve / reject / edit
# ─────────────────────────────────────────────────────────────

@router.patch("/{venture_id}/queue/{item_id}", response_model=QueueItemResponse)
async def patch_queue_item(
    venture_id: str,
    item_id:    str,
    body:       QueuePatchRequest,
    venture:    AnyMember,      # viewers can approve/reject per build plan
    db_pool:    DBPool,
):
    """
    Approve, reject, or edit a queue item inline.

    approve → status = 'approved', sets approved_at
    reject  → status = 'rejected', stores reason in error_message
    edit    → updates title/description/tags/scheduled_for, keeps current status
    """
    # Verify item belongs to this venture
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, venture_id, platform, status, title, description,
                       tags, created_at, scheduled_for
                FROM public.publish_queue
                WHERE id = %s AND venture_id = %s;
            """, (item_id, venture_id))
            row = cur.fetchone()
    finally:
        db_pool.putconn(conn)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue item not found.",
        )

    now = datetime.now(timezone.utc)

    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            if body.action == "approve":
                cur.execute("""
                    UPDATE public.publish_queue
                    SET status = 'approved', approved_at = %s, updated_at = %s
                    WHERE id = %s;
                """, (now, now, item_id))

            elif body.action == "reject":
                cur.execute("""
                    UPDATE public.publish_queue
                    SET status = 'rejected',
                        error_message = %s,
                        updated_at = %s
                    WHERE id = %s;
                """, (body.reason, now, item_id))

            elif body.action == "edit":
                # Only update fields that were actually supplied
                edit_fields = {}
                if body.title         is not None: edit_fields["title"]         = body.title
                if body.description   is not None: edit_fields["description"]   = body.description
                if body.tags          is not None: edit_fields["tags"]          = body.tags
                if body.scheduled_for is not None: edit_fields["scheduled_for"] = body.scheduled_for
                edit_fields["updated_at"] = now

                set_clause = ", ".join(f"{k} = %s" for k in edit_fields)
                values = list(edit_fields.values()) + [item_id]
                cur.execute(
                    f"UPDATE public.publish_queue SET {set_clause} WHERE id = %s;",
                    values,
                )

        conn.commit()
    finally:
        db_pool.putconn(conn)

    # Return the updated row
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, venture_id, platform, status, title, description,
                       tags, created_at, scheduled_for
                FROM public.publish_queue
                WHERE id = %s;
            """, (item_id,))
            updated = cur.fetchone()
    finally:
        db_pool.putconn(conn)

    return QueueItemResponse(
        id=updated[0], venture_id=updated[1], platform=updated[2],
        status=updated[3], title=updated[4], description=updated[5],
        tags=updated[6], created_at=updated[7], scheduled_for=updated[8],
    )
