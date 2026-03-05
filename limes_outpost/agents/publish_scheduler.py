import json
import time
from datetime import datetime, timezone

from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.logger import LimesOutpostLogger


class PublishScheduler:
    """
    Distribution Scheduler.

    Reads 'approved' items from publish_queue and dispatches
    the correct publisher agent based on platform:
      - youtube → PublisherAgent
      - twitter → TwitterPublisherAgent
      - email   → EmailPublisherAgent
      - blog    → logged and skipped (no CMS integration yet)

    Flow per item:
      1. Lock the row by setting status → 'publishing'
      2. Resolve the file_path / metadata from the linked asset
      3. Call the appropriate publisher agent
      4. Update row to 'published' or 'failed'
    """

    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.logger  = LimesOutpostLogger()

    def run(self, platform: str = None):
        """
        Main entry point. Processes all approved queue items.
        Optionally filter by platform (e.g. 'youtube', 'twitter', 'email').
        """
        self.logger.info(
            f"🗓️  Scheduler: Checking publish queue"
            + (f" [{platform}]" if platform else " [all platforms]")
            + "..."
        )

        items = self._fetch_approved_items(platform=platform)

        if not items:
            self.logger.info("✅ Scheduler: Queue is empty — nothing to publish.")
            return {"published": 0, "failed": 0}

        self.logger.info(f"📋 Scheduler: Found {len(items)} approved item(s) to publish.")

        published = 0
        failed    = 0

        for item in items:
            success = self._process_item(item)
            if success:
                published += 1
            else:
                failed += 1

        return {"published": published, "failed": failed}

    # ------------------------------------------------------------------
    # Core dispatch
    # ------------------------------------------------------------------

    def _process_item(self, item):
        queue_id   = item["id"]
        asset_id   = item["asset_id"]
        venture_id = item["venture_id"]
        title      = item["title"]
        platform   = item["platform"]

        self.logger.info(
            f"🚀 Scheduler: Publishing queue item {queue_id} "
            f"— '{title}' → {platform}"
        )

        # Lock row immediately to prevent double-dispatch
        self._update_status(queue_id, "publishing")

        try:
            agent_input = self._build_agent_input(item)
            result      = self._dispatch(platform, venture_id, agent_input)
        except Exception as e:
            self.logger.error(f"❌ Scheduler: Dispatch error for {queue_id}: {e}")
            self._update_status(queue_id, "failed", error_message=str(e), increment_retry=True)
            return False

        if result.get("status") == "published":
            self._update_status(
                queue_id, "published",
                platform_post_id=result.get("platform_post_id"),
                platform_url=result.get("platform_url"),
                published_at=result.get("published_at"),
            )
            self.logger.info(f"✅ Scheduler: Published → {result.get('platform_url')}")
            return True
        else:
            error_msg = result.get("message") or result.get("error", "Unknown error")
            self._update_status(
                queue_id, "failed",
                error_message=error_msg,
                increment_retry=True,
            )
            self.logger.error(f"❌ Scheduler: Publish failed — {error_msg}")
            return False

    def _dispatch(self, platform: str, venture_id: str, agent_input: dict):
        """Routes to the correct publisher agent based on platform."""
        services = {"db_pool": self.db_pool}
        context  = {"venture_id": venture_id}

        if platform == "youtube":
            from limes_outpost.agents.publisher_agent import PublisherAgent
            agent = PublisherAgent(services=services)
            return agent.run(input_data=agent_input, context=context)

        elif platform == "twitter":
            from limes_outpost.agents.twitter_publisher_agent import TwitterPublisherAgent
            agent = TwitterPublisherAgent(services=services)
            return agent.run(input_data=agent_input, context=context)

        elif platform == "email":
            from limes_outpost.agents.email_publisher_agent import EmailPublisherAgent
            agent = EmailPublisherAgent(services=services)
            return agent.run(input_data=agent_input, context=context)

        elif platform == "blog":
            # No CMS integration yet — mark as published with a note
            self.logger.info(
                f"📝 Scheduler: Blog post approved — no CMS publisher wired yet. "
                f"File is at: {agent_input.get('file_path', 'unknown')}"
            )
            return {
                "status":           "published",
                "platform_post_id": "local",
                "platform_url":     agent_input.get("file_path", ""),
                "published_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

        else:
            raise ValueError(f"Unknown platform: '{platform}'")

    def _build_agent_input(self, item: dict) -> dict:
        """
        Builds the input dict for the publisher agent.
        For email, extracts metadata from the tags array JSON string.
        For youtube/twitter/blog, resolves file_path from assets table.
        """
        platform   = item["platform"]
        venture_id = item["venture_id"]

        base = {
            "venture_id":  venture_id,
            "title":       item.get("title") or "",
            "description": item.get("description") or "",
            "tags":        item.get("tags") or [],
        }

        if platform == "email":
            # Email metadata is stored as a JSON string in tags[0]
            meta = {}
            tags = item.get("tags") or []
            if tags:
                try:
                    meta = json.loads(tags[0])
                except Exception:
                    pass
            base.update({
                "to":               meta.get("to", ""),
                "subject":          item.get("title", ""),
                "body":             item.get("description", ""),
                "gmail_thread_id":  meta.get("gmail_thread_id", ""),
                "gmail_message_id": meta.get("gmail_message_id", ""),
            })
            return base

        elif platform == "twitter":
            base["tweet_text"] = item.get("description") or item.get("title") or ""
            return base

        else:
            # youtube / blog — resolve file path from assets table
            file_path = self._resolve_file_path(item.get("asset_id"))
            base["file_path"] = file_path or ""
            base["asset_id"]  = str(item.get("asset_id") or "")
            return base

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _fetch_approved_items(self, platform: str = None):
        """Returns approved queue items, optionally filtered by platform."""
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cur:
                if platform:
                    cur.execute("""
                        SELECT
                            id, asset_id, venture_id, platform,
                            title, description, tags,
                            scheduled_for, retry_count
                        FROM public.publish_queue
                        WHERE status = 'approved'
                          AND platform = %s
                          AND (scheduled_for IS NULL OR scheduled_for <= NOW())
                        ORDER BY COALESCE(scheduled_for, created_at) ASC;
                    """, (platform,))
                else:
                    cur.execute("""
                        SELECT
                            id, asset_id, venture_id, platform,
                            title, description, tags,
                            scheduled_for, retry_count
                        FROM public.publish_queue
                        WHERE status = 'approved'
                          AND (scheduled_for IS NULL OR scheduled_for <= NOW())
                        ORDER BY COALESCE(scheduled_for, created_at) ASC;
                    """)
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            self.db_pool.putconn(conn)

    def _resolve_file_path(self, asset_id):
        """Looks up file_path in assets table for a given asset UUID."""
        if not asset_id:
            return None
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT file_path FROM public.assets WHERE id = %s",
                    (str(asset_id),)
                )
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            self.db_pool.putconn(conn)

    def _update_status(
        self, queue_id, status,
        platform_post_id=None,
        platform_url=None,
        published_at=None,
        error_message=None,
        increment_retry=False,
    ):
        """Updates a queue row's status and optional outcome fields."""
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE public.publish_queue SET
                        status           = %s,
                        platform_post_id = COALESCE(%s, platform_post_id),
                        platform_url     = COALESCE(%s, platform_url),
                        published_at     = COALESCE(%s::timestamptz, published_at),
                        error_message    = COALESCE(%s, error_message),
                        retry_count      = CASE WHEN %s THEN retry_count + 1 ELSE retry_count END,
                        updated_at       = NOW()
                    WHERE id = %s;
                """, (
                    status,
                    platform_post_id,
                    platform_url,
                    published_at,
                    error_message,
                    increment_retry,
                    str(queue_id),
                ))
                conn.commit()
        finally:
            self.db_pool.putconn(conn)