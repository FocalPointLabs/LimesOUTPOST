"""
limes_outpost.api.routers.analytics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
GET /ventures/{venture_id}/analytics
GET /ventures/{venture_id}/analytics/feed
"""

from typing import Optional
from fastapi import APIRouter

from limes_outpost.api.dependencies import DBPool, AnyMember
from limes_outpost.api.schemas import AnalyticsSummaryResponse, AnalyticsFeedResponse, AnalyticsFeedItem

router = APIRouter()


# ─────────────────────────────────────────────────────────────
#  Summary
# ─────────────────────────────────────────────────────────────

@router.get("/{venture_id}/analytics", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    venture_id: str,
    venture:    AnyMember,
    db_pool:    DBPool,
    platform:   Optional[str] = "youtube",
):
    """
    Returns a high-level metrics summary for the venture.
    Aggregates analytics_events for the most recent snapshot per asset.

    Until Phase 5 (YouTubeAnalyticsAgent) runs, this will return nulls —
    that's correct, not a bug.
    """
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    SUM(CASE WHEN metric_type = 'views'  THEN metric_value END) AS total_views,
                    SUM(CASE WHEN metric_type = 'likes'  THEN metric_value END) AS total_likes,
                    AVG(CASE WHEN metric_type = 'ctr'    THEN metric_value END) AS avg_ctr,
                    MAX(recorded_at) AS as_of
                FROM public.analytics_events
                WHERE venture_id = %s
                  AND platform   = %s;
            """, (venture_id, platform))
            agg = cur.fetchone()

            # Top performing asset by views
            cur.execute("""
                SELECT asset_id
                FROM public.analytics_events
                WHERE venture_id  = %s
                  AND platform    = %s
                  AND metric_type = 'views'
                  AND asset_id IS NOT NULL
                ORDER BY metric_value DESC
                LIMIT 1;
            """, (venture_id, platform))
            top = cur.fetchone()
    finally:
        db_pool.putconn(conn)

    return AnalyticsSummaryResponse(
        venture_id=venture_id,
        platform=platform,
        total_views=agg[0],
        total_likes=agg[1],
        avg_ctr=float(agg[2]) if agg[2] else None,
        top_asset_id=top[0] if top else None,
        as_of=agg[3],
    )


# ─────────────────────────────────────────────────────────────
#  Feed (paginated event log)
# ─────────────────────────────────────────────────────────────

@router.get("/{venture_id}/analytics/feed", response_model=AnalyticsFeedResponse)
async def get_analytics_feed(
    venture_id: str,
    venture:    AnyMember,
    db_pool:    DBPool,
    platform:   Optional[str] = None,
    page:       int = 1,
    page_size:  int = 50,
):
    """
    Returns a paginated log of raw analytics events, newest first.
    Useful for dashboards showing recent metric activity.
    """
    offset = (page - 1) * page_size

    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT id, asset_id, platform, metric_type,
                       metric_value, recorded_at
                FROM public.analytics_events
                WHERE venture_id = %s
            """
            params = [venture_id]

            if platform:
                query += " AND platform = %s"
                params.append(platform)

            query += " ORDER BY recorded_at DESC LIMIT %s OFFSET %s;"
            params += [page_size, offset]

            cur.execute(query, params)
            rows = cur.fetchall()
    finally:
        db_pool.putconn(conn)

    items = [
        AnalyticsFeedItem(
            id=r[0], asset_id=r[1], platform=r[2],
            metric_type=r[3], metric_value=r[4], recorded_at=r[5],
        )
        for r in rows
    ]

    return AnalyticsFeedResponse(
        venture_id=venture_id,
        page=page,
        page_size=page_size,
        items=items,
    )
