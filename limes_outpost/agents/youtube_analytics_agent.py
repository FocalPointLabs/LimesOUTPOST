"""
limes_outpost.agents.youtube_analytics_agent
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Phase 5: Analytics feedback loop.

Pulls per-video metrics from the YouTube Analytics API v2 for all
published assets belonging to a venture, and writes rows to the
analytics_events table.

Metrics pulled per video (last 30 days):
  views, likes, comments, shares, estimatedMinutesWatched, averageViewDuration

Auth
----
Reuses the same OAuth pattern as PublisherAgent:
  - Token cached at ventures/{venture_id}/youtube_analytics_token.pickle
  - Separate cache from upload token to avoid scope collision
  - Scope: yt-analytics.readonly (read-only, no upload permission needed)
  - First run: browser consent flow (same client_secrets.json)
  - Subsequent runs: silent token refresh

Scheduling
----------
Registered by Beat as a daily low-priority task per venture.
Wired in limes_outpost/tasks/pipeline_tasks.py → pull_analytics().

Dry run
-------
Returns mock analytics rows without touching the YouTube API or DB.
"""

import os
import pickle
import json
from datetime import datetime, timedelta, timezone

from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled

# Google API client libs
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ── Constants ────────────────────────────────────────────────

ANALYTICS_SCOPE       = ["https://www.googleapis.com/auth/yt-analytics.readonly"]
TOKEN_CACHE_TEMPLATE  = "ventures/{venture_id}/youtube_analytics_token.pickle"
CLIENT_SECRETS_PATH   = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")

# Metrics to pull — maps YouTube Analytics dimension name → our metric_type
METRIC_MAP = {
    "views":                    "views",
    "likes":                    "likes",
    "comments":                 "comments",
    "shares":                   "shares",
    "estimatedMinutesWatched":  "watch_time",
    "averageViewDuration":      "avg_view_duration",
}

LOOKBACK_DAYS = 30


class YouTubeAnalyticsAgent(BaseAgent):
    """
    Pulls YouTube Analytics metrics for all published assets of a venture
    and writes rows to analytics_events.

    One analytics_events row per (asset, metric_type, pull date).
    Append-only — never updates existing rows.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="youtube_analytics", services=services)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, input_data, context, campaign_id=None):
        venture_id = self.get_venture_id(context)

        if dry_run_enabled():
            return self.dry_run(input_data, context)
        return self.live_run(venture_id)

    # ------------------------------------------------------------------
    # Live run
    # ------------------------------------------------------------------

    def live_run(self, venture_id: str) -> dict:
        self.logger.info(f"📊 [YouTubeAnalytics] Starting pull for venture: {venture_id}")

        db_pool = self.get_service("db_pool")
        if not db_pool:
            return {"status": "error", "message": "No DB pool available."}

        # 1. Get authenticated YouTube Analytics service
        try:
            yta_service = self._get_authenticated_service(venture_id)
        except Exception as e:
            self.logger.error(f"❌ [YouTubeAnalytics] Auth failed: {e}")
            return {"status": "error", "message": f"YouTube Analytics auth failed: {e}"}

        # 2. Fetch published video IDs for this venture from publish_queue
        published = self._fetch_published_assets(db_pool, venture_id)
        if not published:
            self.logger.info(f"[YouTubeAnalytics] No published assets found for {venture_id}.")
            return {"status": "success", "pulled": 0, "venture_id": venture_id}

        self.logger.info(f"[YouTubeAnalytics] Found {len(published)} published asset(s).")

        # 3. Pull metrics and write to DB
        end_date   = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=LOOKBACK_DAYS)
        recorded_at = datetime.now(timezone.utc)

        total_rows = 0
        for asset_id, video_id in published:
            try:
                metrics = self._pull_video_metrics(
                    yta_service, video_id, str(start_date), str(end_date)
                )
                rows_written = self._write_analytics_events(
                    db_pool, venture_id, asset_id, metrics, recorded_at
                )
                total_rows += rows_written
                self.logger.info(
                    f"[YouTubeAnalytics] {video_id} → {rows_written} metric row(s) written."
                )
            except Exception as e:
                self.logger.warning(
                    f"⚠️ [YouTubeAnalytics] Failed to pull metrics for video {video_id}: {e}"
                )
                continue

        self.logger.info(
            f"✅ [YouTubeAnalytics] Pull complete for {venture_id}: "
            f"{total_rows} total rows written."
        )
        return {
            "status":     "success",
            "venture_id": venture_id,
            "assets":     len(published),
            "rows":       total_rows,
        }

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    def dry_run(self, input_data, context) -> dict:
        venture_id = self.get_venture_id(context)
        self.logger.info(f"🧪 [YouTubeAnalytics] DRY RUN for venture: {venture_id}")
        return {
            "status":     "success",
            "venture_id": venture_id,
            "assets":     2,
            "rows":       12,
            "dry_run":    True,
            "note":       "Mock metrics — no YouTube API call made.",
        }

    # ------------------------------------------------------------------
    # YouTube Analytics API
    # ------------------------------------------------------------------

    def _pull_video_metrics(
        self,
        service,
        video_id: str,
        start_date: str,
        end_date: str,
    ) -> dict:
        """
        Pulls aggregated metrics for a single video over the date range.
        Returns a dict of {metric_type: value}.
        """
        dimensions_str = ",".join(METRIC_MAP.keys())

        response = (
            service.reports()
            .query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics=dimensions_str,
                filters=f"video=={video_id}",
            )
            .execute()
        )

        rows = response.get("rows", [])
        if not rows:
            return {}

        # rows[0] is a flat list matching the metrics order
        col_headers = [h["name"] for h in response.get("columnHeaders", [])]
        values      = rows[0]

        result = {}
        for col, val in zip(col_headers, values):
            metric_type = METRIC_MAP.get(col)
            if metric_type and val is not None:
                result[metric_type] = float(val)

        return result

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _fetch_published_assets(self, db_pool, venture_id: str) -> list[tuple]:
        """
        Returns list of (asset_id, platform_post_id) for all published
        YouTube assets belonging to this venture.
        """
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT asset_id, platform_post_id
                    FROM public.publish_queue
                    WHERE venture_id       = %s
                      AND platform         = 'youtube'
                      AND status           = 'published'
                      AND platform_post_id IS NOT NULL
                      AND asset_id         IS NOT NULL;
                """, (venture_id,))
                return cur.fetchall()
        finally:
            db_pool.putconn(conn)

    def _write_analytics_events(
        self,
        db_pool,
        venture_id: str,
        asset_id,
        metrics: dict,
        recorded_at: datetime,
    ) -> int:
        """
        Inserts one analytics_events row per metric.
        Append-only — never updates existing rows.
        Returns the number of rows written.
        """
        if not metrics:
            return 0

        conn = db_pool.getconn()
        rows_written = 0
        try:
            with conn.cursor() as cur:
                for metric_type, metric_value in metrics.items():
                    cur.execute("""
                        INSERT INTO public.analytics_events
                            (venture_id, asset_id, platform, metric_type,
                             metric_value, recorded_at)
                        VALUES (%s, %s, 'youtube', %s, %s, %s);
                    """, (
                        venture_id,
                        str(asset_id),
                        metric_type,
                        metric_value,
                        recorded_at,
                    ))
                    rows_written += 1
            conn.commit()
        finally:
            db_pool.putconn(conn)

        return rows_written

    # ------------------------------------------------------------------
    # Auth — mirrors PublisherAgent._get_authenticated_service exactly,
    # with a different scope and separate token cache path.
    # ------------------------------------------------------------------

    def _get_authenticated_service(self, venture_id: str):
        """
        Loads cached OAuth token or runs first-time browser consent flow.
        Uses a separate token cache from PublisherAgent to avoid scope collision.
        """
        token_path = TOKEN_CACHE_TEMPLATE.format(venture_id=venture_id)
        creds = None

        if os.path.exists(token_path):
            with open(token_path, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                self.logger.info("🔄 [YouTubeAnalytics] Refreshing expired token...")
                creds.refresh(Request())
            else:
                self.logger.info("🔐 [YouTubeAnalytics] Opening browser for OAuth consent...")
                if not os.path.exists(CLIENT_SECRETS_PATH):
                    raise FileNotFoundError(
                        f"client_secrets.json not found at '{CLIENT_SECRETS_PATH}'. "
                        f"Download from Google Cloud Console → APIs & Services → Credentials."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRETS_PATH,
                    scopes=ANALYTICS_SCOPE,
                )
                creds = flow.run_local_server(port=0)

            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, "wb") as f:
                pickle.dump(creds, f)
            self.logger.info(f"💾 [YouTubeAnalytics] Token cached at {token_path}")

        return build("youtubeAnalytics", "v2", credentials=creds)
