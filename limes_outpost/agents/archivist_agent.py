import json
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.integrations.discord import OutpostSignalClient
from limes_outpost.integrations.channel_adapter import LimesOutpostAdapter


class ArchivistAgent(BaseAgent):
    """
    Post-pipeline archivist. Runs after all pipeline steps complete.
    Reads completed content_items for a campaign and writes one assets row
    per step that produced a file, using the compound content_item_id as the FK.

    Archivable steps and what they produce:
      - voiceover_phase      -> single audio file (audio_file_path)
      - visual_phase         -> N scene video files (scenes[].video_file_path)
      - composition_phase    -> final composed video -> also enqueued to publish_queue (youtube)
      - blog_formatter_phase -> markdown article file -> assets + publish_queue (blog)
      - social_script_phase  -> tweet text -> publish_queue ONLY (no file asset, asset_id=NULL)

    All other steps produce no archivable output and are silently skipped.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="archivist", services=services)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, input_data, context, campaign_id=None):
        target_id = campaign_id or input_data.get("campaign_id")
        result    = self.archive_campaign_assets(target_id, context)

        # Trigger Signal for the Mayor
        try:
            venture_id = (self.get_brand(context) or {}).get("venture_id", "unknown") if context else "unknown"
            signal = OutpostSignalClient()
            adapter = LimesOutpostAdapter(signal)
            
            # We broadcast that the campaign is now 'archived' and ready
            adapter.broadcast_item_queued(
                venture_id=venture_id,
                asset_type="Production Batch", 
                title=f"Campaign {target_id} Assets Finalized",
                campaign_id=target_id
            )
        except Exception as e:
            self.logger.warning(f"⚠️ Archivist Signal failed: {e}")

        return {"status": "success", "summary": result}

    def archive_campaign_assets(self, campaign_id, context=None):
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return "No DB Pool"

        # Resolve venture_id once up front for all inserts
        venture_id = (self.get_brand(context) or {}).get("venture_id", "unknown") if context else "unknown"

        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, topic, script_data
                    FROM public.content_items
                    WHERE campaign_id = %s AND status = 'completed';
                """, (campaign_id,))
                items = cur.fetchall()

            if not items:
                return f"No completed steps found for campaign {campaign_id}"

            archived_count = 0
            enqueued_count = 0
            social_count   = 0
            skipped        = []

            for content_item_id, topic, raw_data in items:
                data = raw_data if isinstance(raw_data, dict) else json.loads(raw_data or "{}")

                # Social steps go straight to publish_queue - no file asset produced
                # asset_id is NULL for social posts (no file in assets table)
                if topic == "social_script_phase":
                    enqueued = self._enqueue_social_post(
                        conn=conn,
                        campaign_id=campaign_id,
                        venture_id=venture_id,
                        data=data,
                        context=context,
                    )
                    if enqueued:
                        social_count += 1
                    continue

                extraction = self._extract_asset(topic, data)
                if extraction is None:
                    skipped.append(topic)
                    continue

                file_path, file_type, metadata = extraction
                clean_path = file_path.replace("\\", "/")

                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO public.assets
                            (content_item_id, file_path, file_type, metadata, venture_id, status)
                        VALUES (%s, %s, %s, %s, %s, 'pending_review')
                        ON CONFLICT (content_item_id)
                        DO UPDATE SET
                            file_path  = EXCLUDED.file_path,
                            file_type  = EXCLUDED.file_type,
                            metadata   = EXCLUDED.metadata,
                            venture_id = EXCLUDED.venture_id,
                            status     = EXCLUDED.status
                        RETURNING id;
                    """, (
                        content_item_id,
                        clean_path,
                        file_type,
                        json.dumps(metadata) if metadata else None,
                        venture_id,
                    ))
                    asset_row = cur.fetchone()

                    # Fallback: if RETURNING gave nothing, fetch the existing row
                    if not asset_row:
                        cur.execute(
                            "SELECT id FROM public.assets WHERE content_item_id = %s",
                            (content_item_id,)
                        )
                        asset_row = cur.fetchone()

                    archived_count += 1

                    # Enqueue final video for YouTube publish review
                    if topic == "composition_phase" and asset_row:
                        asset_id = asset_row[0]
                        enqueued = self._enqueue_for_publish(
                            conn=conn,
                            asset_id=asset_id,
                            campaign_id=campaign_id,
                            venture_id=venture_id,
                            data=data,
                            context=context,
                        )
                        if enqueued:
                            enqueued_count += 1

                    # Enqueue blog post for review
                    if topic == "blog_formatter_phase" and asset_row:
                        asset_id = asset_row[0]
                        enqueued = self._enqueue_for_blog(
                            conn=conn,
                            asset_id=asset_id,
                            campaign_id=campaign_id,
                            venture_id=venture_id,
                            data=data,
                        )
                        if enqueued:
                            enqueued_count += 1

            conn.commit()

            summary = f"Archived {archived_count} asset(s) for campaign {campaign_id}"
            if enqueued_count:
                summary += f" | {enqueued_count} item(s) queued for review"
            if social_count:
                summary += f" | {social_count} tweet(s) queued for review"
            if skipped:
                summary += f" (skipped non-file steps: {', '.join(skipped)})"
            return summary

        except Exception as e:
            conn.rollback()
            self.logger.error(f"Archive failed for campaign {campaign_id}: {e}")
            raise

        finally:
            db_pool.putconn(conn)

    # ------------------------------------------------------------------
    # Publish queue - video
    # ------------------------------------------------------------------

    def _enqueue_for_publish(self, conn, asset_id, campaign_id, venture_id, data, context):
        """Inserts a YouTube publish_queue row with status 'pending_review'."""
        try:
            brand      = self.get_brand(context) if context else {}
            brand_name = brand.get("name", "")
            niche      = brand.get("niche", "Wellness")

            title       = f"{brand_name} | {niche} Short" if brand_name else f"{niche} Short"
            description = (
                f"Follow for daily {niche.lower()} content.\n\n"
                f"#Shorts #{niche.replace(' ', '')} #Wellness"
            )
            tags = [niche.lower(), "shorts", "wellness", "youtube shorts"]

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.publish_queue
                        (asset_id, venture_id, platform, status, title, description, tags)
                    VALUES (%s, %s, 'youtube', 'pending_review', %s, %s, %s)
                    ON CONFLICT DO NOTHING;
                """, (str(asset_id), venture_id, title, description, tags))

            self.logger.info(
                f"[Archivist] Queued asset {asset_id} for YouTube review "
                f"(campaign {campaign_id})"
            )
            return True

        except Exception as e:
            self.logger.warning(f"[Archivist] Failed to enqueue video for publish: {e}")
            return False

    # ------------------------------------------------------------------
    # Publish queue - blog
    # ------------------------------------------------------------------

    def _enqueue_for_blog(self, conn, asset_id, campaign_id, venture_id, data):
        """Inserts a blog publish_queue row with status 'pending_review'."""
        try:
            title       = data.get("title", "Untitled Blog Post")
            description = data.get("meta_description", "")
            tags        = [data.get("primary_keyword", "")]

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.publish_queue
                        (asset_id, venture_id, platform, status, title, description, tags)
                    VALUES (%s, %s, 'blog', 'pending_review', %s, %s, %s)
                    ON CONFLICT DO NOTHING;
                """, (str(asset_id), venture_id, title, description, tags))

            self.logger.info(
                f"[Archivist] Queued blog post for review (campaign {campaign_id})"
            )
            return True

        except Exception as e:
            self.logger.warning(f"[Archivist] Failed to enqueue blog post: {e}")
            return False

    # ------------------------------------------------------------------
    # Publish queue - social (no asset row, asset_id=NULL)
    # ------------------------------------------------------------------

    def _enqueue_social_post(self, conn, campaign_id, venture_id, data, context):
        """Inserts a Twitter publish_queue row directly from social_script_output.

        No asset row is written - tweet text is stored in description.
        asset_id is NULL since there is no file asset for a tweet.
        """
        try:
            tweet_text = data.get("tweet_text", "")
            topic      = data.get("topic", "")
            hook       = data.get("hook", "")

            if not tweet_text:
                self.logger.warning("[Archivist] social_script_phase: no tweet_text found.")
                return False

            title = f"Tweet: {hook[:80]}" if hook else f"Tweet about {topic[:80]}"

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.publish_queue
                        (venture_id, platform, status, title, description, tags)
                    VALUES (%s, 'twitter', 'pending_review', %s, %s, %s)
                    ON CONFLICT DO NOTHING;
                """, (
                    venture_id,
                    title,
                    tweet_text,
                    data.get("hashtags", []),
                ))

            self.logger.info(
                f"[Archivist] Queued tweet for review (campaign {campaign_id}): "
                f"'{tweet_text[:60]}...'"
            )
            return True

        except Exception as e:
            self.logger.warning(f"[Archivist] Failed to enqueue social post: {e}")
            return False

    # ------------------------------------------------------------------
    # Asset extraction
    # ------------------------------------------------------------------

    def _extract_asset(self, topic, data):
        if topic == "voiceover_phase":
            return self._extract_voiceover(data)
        if topic == "visual_phase":
            return self._extract_visual(data)
        if topic == "composition_phase":
            return self._extract_composition(data)
        if topic == "blog_formatter_phase":
            return self._extract_blog(data)
        return None

    def _extract_voiceover(self, data):
        path = data.get("audio_file_path")
        if not path:
            self.logger.warning("[Archivist] voiceover_phase: no audio_file_path found")
            return None
        return path, "audio", None

    def _extract_visual(self, data):
        scenes      = data.get("scenes", [])
        video_paths = [
            s.get("video_file_path") for s in scenes
            if s.get("video_file_path") and "pending" not in str(s.get("video_file_path"))
        ]
        if not video_paths:
            self.logger.warning("[Archivist] visual_phase: no completed scene video paths found")
            return None
        metadata = {"all_scene_paths": video_paths, "scene_count": len(video_paths)}
        return video_paths[0], "video", metadata

    def _extract_composition(self, data):
        path = data.get("local_video_path") or data.get("url")
        if not path:
            self.logger.warning("[Archivist] composition_phase: no local_video_path or url found")
            return None
        return path, "video", None

    def _extract_blog(self, data):
        path = data.get("file_path")
        if not path:
            self.logger.warning("[Archivist] blog_formatter_phase: no file_path found")
            return None
        metadata = {
            "title":                data.get("title", ""),
            "primary_keyword":      data.get("primary_keyword", ""),
            "meta_description":     data.get("meta_description", ""),
            "word_count":           data.get("word_count", 0),
            "primary_keyword_used": data.get("primary_keyword_used", False),
            "cta_included":         data.get("cta_included", False),
        }
        return path, "markdown", metadata