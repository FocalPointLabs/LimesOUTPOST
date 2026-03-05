from limes_outpost.agents.base_agent import BaseAgent
import json

class IntelStrategyAgent(BaseAgent):
    def __init__(self, services=None):
        super().__init__(agent_id="intel_strategy", services=services)

    def run(self, input_data, context, campaign_id=None):
        brand_dna = self.get_brand(context)
        venture_id = self.get_venture_id(context)

        # 1. Fetch the articles found by the Intel Agent
        intel_list = self._get_latest_intel(venture_id)

        # 2. SELECTION LOGIC: pick the first article not already used
        primary_trend = None

        if intel_list:
            used_headlines = self._get_used_headlines(venture_id)

            for entry in intel_list:
                try:
                    article = json.loads(entry) if isinstance(entry, str) else entry
                    title = article.get('title')
                except:
                    title = entry  # Fallback to raw string

                if title and title not in used_headlines:
                    primary_trend = title
                    break

            # All articles already used — fall back to least-recently-used
            if not primary_trend:
                self.logger.warning("⚠️ [IntelStrategy] All recent articles already used. Recycling oldest.")
                try:
                    first_article = json.loads(intel_list[0]) if isinstance(intel_list[0], str) else intel_list[0]
                    primary_trend = first_article.get('title', input_data.get("manual_query"))
                except:
                    primary_trend = intel_list[0]

        # 3. Final fallback to manual query
        if not primary_trend:
            primary_trend = input_data.get("manual_query") if isinstance(input_data, dict) else None
            primary_trend = primary_trend or f"Morning {brand_dna.get('niche', 'Wellness')}"

        # 4. Record the selected headline so it's excluded next time
        self._mark_headline_used(venture_id, primary_trend)

        # 5. Create the Directive
        # inspiration_source is the raw headline — consumed by both video and blog pipelines.
        # production_prompt is video-framed language for backwards compatibility with StrategyAgent.
        niche = brand_dna.get("niche") or "Wellness"
        directive = {
            "inspiration_source": primary_trend,
            "production_prompt": f"Create a high-impact video strategy about '{primary_trend}' tailored for the {niche} niche.",
        }

        return {
            "status": "success",
            "venture_id": venture_id,
            "directive": directive,
            "summary": f"🚀 RESEARCH-BACKED: Targeting '{primary_trend[:50]}'"
        }

    def _get_latest_intel(self, venture_id):
        """Fetches the most recent articles stored by IntelAgent."""
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return []
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT content FROM public.market_intel
                    WHERE venture_id = %s
                    AND intel_type != 'selected_trend'
                    ORDER BY created_at DESC LIMIT 10;
                """, (venture_id,))
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            self.logger.warning(f"⚠️ Intel DB Error: {e}")
            return []
        finally:
            db_pool.putconn(conn)

    def _get_used_headlines(self, venture_id):
        """Returns a set of headlines already selected for this venture."""
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return set()
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT content FROM public.market_intel
                    WHERE venture_id = %s
                    AND intel_type = 'selected_trend'
                    ORDER BY created_at DESC LIMIT 50;
                """, (venture_id,))
                return {row[0] for row in cur.fetchall()}
        except Exception as e:
            self.logger.warning(f"⚠️ Intel DB Error (used headlines): {e}")
            return set()
        finally:
            db_pool.putconn(conn)

    def _mark_headline_used(self, venture_id, headline):
        """Persists the selected headline so it won't be picked again."""
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.market_intel (venture_id, intel_type, content)
                    VALUES (%s, 'selected_trend', %s);
                """, (venture_id, headline))
                conn.commit()
        except Exception as e:
            self.logger.warning(f"⚠️ Intel DB Error (mark used): {e}")
        finally:
            db_pool.putconn(conn)