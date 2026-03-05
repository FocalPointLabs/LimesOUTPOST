"""
limes_outpost.api.routers.inbox
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from limes_outpost.api.dependencies import DBPool, OperatorOnly

router = APIRouter()

class WhitelistRequest(BaseModel):
    email: str


@router.get("")
async def list_threads(
    venture_id: str, venture: OperatorOnly, db: DBPool,
    status_filter: str = Query("all"), limit: int = Query(100),
):
    conn = db.getconn()
    try:
        with conn.cursor() as cur:
            if status_filter == "all":
                cur.execute("""
                    SELECT id, gmail_thread_id, sender_email, sender_name,
                           subject, body_snippet, category, priority_score,
                           is_whitelisted, triage_notes, status, created_at, updated_at
                    FROM public.email_threads WHERE venture_id = %s
                    ORDER BY priority_score DESC NULLS LAST, created_at DESC LIMIT %s;
                """, (venture_id, limit))
            else:
                cur.execute("""
                    SELECT id, gmail_thread_id, sender_email, sender_name,
                           subject, body_snippet, category, priority_score,
                           is_whitelisted, triage_notes, status, created_at, updated_at
                    FROM public.email_threads WHERE venture_id = %s AND status = %s
                    ORDER BY priority_score DESC NULLS LAST, created_at DESC LIMIT %s;
                """, (venture_id, status_filter, limit))
            cols = [d[0] for d in cur.description]
            threads = [dict(zip(cols, row)) for row in cur.fetchall()]
            for t in threads:
                if t.get("created_at"): t["created_at"] = t["created_at"].isoformat()
                if t.get("updated_at"): t["updated_at"] = t["updated_at"].isoformat()
        return {"threads": threads}
    finally:
        db.putconn(conn)


@router.post("/run")
async def trigger_email_cycle(venture_id: str, venture: OperatorOnly):
    from limes_outpost.tasks.email_tasks import run_email_cycle as _task
    task = _task.delay(venture_id=venture_id)
    return {"task_id": task.id, "platform": "email"}


@router.post("/whitelist")
async def add_whitelist(venture_id: str, body: WhitelistRequest, venture: OperatorOnly, db: DBPool):
    conn = db.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE public.ventures
                SET whitelisted_emails = array_append(COALESCE(whitelisted_emails, '{}'), %s)
                WHERE id = %s AND NOT (%s = ANY(COALESCE(whitelisted_emails, '{}')));
            """, (body.email.lower(), venture_id, body.email.lower()))
            conn.commit()
        return {"status": "ok", "email": body.email}
    finally:
        db.putconn(conn)


@router.delete("/whitelist")
async def remove_whitelist(venture_id: str, body: WhitelistRequest, venture: OperatorOnly, db: DBPool):
    conn = db.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.ventures SET whitelisted_emails = array_remove(whitelisted_emails, %s) WHERE id = %s;",
                (body.email.lower(), venture_id)
            )
            conn.commit()
        return {"status": "ok", "email": body.email}
    finally:
        db.putconn(conn)


# ── Social mentions ───────────────────────────────────────────

@router.get("/social")
async def list_mentions(
    venture_id: str, venture: OperatorOnly, db: DBPool,
    status_filter: str = Query("all"), limit: int = Query(100),
):
    conn = db.getconn()
    try:
        with conn.cursor() as cur:
            if status_filter == "all":
                cur.execute("""
                    SELECT id, mention_id, platform, author_username, author_id,
                           text, conversation_id, in_reply_to_id,
                           category, priority_score, is_whitelisted,
                           triage_notes, status, created_at, updated_at
                    FROM public.social_mentions WHERE venture_id = %s
                    ORDER BY priority_score DESC NULLS LAST, created_at DESC LIMIT %s;
                """, (venture_id, limit))
            else:
                cur.execute("""
                    SELECT id, mention_id, platform, author_username, author_id,
                           text, conversation_id, in_reply_to_id,
                           category, priority_score, is_whitelisted,
                           triage_notes, status, created_at, updated_at
                    FROM public.social_mentions WHERE venture_id = %s AND status = %s
                    ORDER BY priority_score DESC NULLS LAST, created_at DESC LIMIT %s;
                """, (venture_id, status_filter, limit))
            cols = [d[0] for d in cur.description]
            mentions = [dict(zip(cols, row)) for row in cur.fetchall()]
            for m in mentions:
                if m.get("created_at"): m["created_at"] = m["created_at"].isoformat()
                if m.get("updated_at"): m["updated_at"] = m["updated_at"].isoformat()
        return {"mentions": mentions}
    finally:
        db.putconn(conn)


@router.post("/social/{mention_id}/ignore")
async def ignore_mention(venture_id: str, mention_id: str, venture: OperatorOnly, db: DBPool):
    conn = db.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.social_mentions SET status = 'ignored', updated_at = NOW() WHERE id = %s AND venture_id = %s;",
                (mention_id, venture_id)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Mention not found.")
            conn.commit()
        return {"status": "ok", "mention_id": mention_id}
    finally:
        db.putconn(conn)


@router.post("/social/{mention_id}/whitelist")
async def whitelist_mention_author(venture_id: str, mention_id: str, venture: OperatorOnly, db: DBPool):
    conn = db.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT author_username FROM public.social_mentions WHERE id = %s AND venture_id = %s",
                (mention_id, venture_id)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Mention not found.")
            username = row[0].lower()
            cur.execute("""
                UPDATE public.ventures
                SET whitelisted_emails = array_append(COALESCE(whitelisted_emails, '{}'), %s)
                WHERE id = %s AND NOT (%s = ANY(COALESCE(whitelisted_emails, '{}')));
            """, (username, venture_id, username))
            cur.execute(
                "UPDATE public.social_mentions SET is_whitelisted = true, updated_at = NOW() WHERE id = %s;",
                (mention_id,)
            )
            conn.commit()
        return {"status": "ok", "username": username}
    finally:
        db.putconn(conn)


@router.delete("/social/{mention_id}/whitelist")
async def unwhitelist_mention_author(venture_id: str, mention_id: str, venture: OperatorOnly, db: DBPool):
    conn = db.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT author_username FROM public.social_mentions WHERE id = %s AND venture_id = %s",
                (mention_id, venture_id)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Mention not found.")
            username = row[0].lower()
            cur.execute(
                "UPDATE public.ventures SET whitelisted_emails = array_remove(whitelisted_emails, %s) WHERE id = %s;",
                (username, venture_id)
            )
            cur.execute(
                "UPDATE public.social_mentions SET is_whitelisted = false, updated_at = NOW() WHERE id = %s;",
                (mention_id,)
            )
            conn.commit()
        return {"status": "ok", "username": username}
    finally:
        db.putconn(conn)