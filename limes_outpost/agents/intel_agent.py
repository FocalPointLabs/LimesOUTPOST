from newsdataapi import NewsDataApiClient
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled
import os
import json

class IntelAgent(BaseAgent):
    def __init__(self, services=None):
        super().__init__(agent_id="intel_agent", services=services)
        api_key = os.getenv("NEWSDATA_API_KEY")
        self.api = NewsDataApiClient(apikey=api_key)

    def run(self, input_data, context, campaign_id="default_campaign"):
        brand_snapshot = self.get_brand(context)
        venture_id = self.get_venture_id(context)

        allowed_categories = brand_snapshot.get("news_categories")
        category_string = ",".join(allowed_categories) if allowed_categories else None

        manual_query = input_data.get("manual_query") if isinstance(input_data, dict) else None
        brand_niche = brand_snapshot.get('niche', 'General')

        # Build relevance keywords from the brand profile so filtering
        # stays niche-aware without any hardcoding here
        rules = brand_snapshot.get('rules', {})
        relevance_keywords = list(set(
            [kw.lower() for kw in rules.get('in_scope_topics', [])] +
            [kw.lower() for kw in rules.get('approved_vocabulary', [])] +
            [brand_niche.lower()]
        ))

        query_candidates = self._build_query_candidates(manual_query, brand_niche)

        if dry_run_enabled():
            self.logger.info(f"🧪 Intel Agent [MOCK]: Simulating news for '{query_candidates[0]}' in categories: {category_string or 'All'}")
            # In dry run, save a mock article to DB so IntelStrategyAgent has something to pick
            self.save_intel(
                venture_id=venture_id,
                intel_type="trending_topic",
                content=f"Simulated trend for {query_candidates[0]}",
                metadata={"title": f"Simulated trend for {query_candidates[0]}", "source": "mock"}
            )
            return {
                "status": "success",
                "articles": [{"title": f"Simulated trend for {query_candidates[0]}"}],
                "summary": f"MOCK: Found 1 trend for '{query_candidates[0]}'."
            }

        # Try each query candidate until we get relevant results
        for query in query_candidates:
            self.logger.info(f"📡 Intel Agent [LIVE]: Querying NewsData.io for '{query}' in categories: {category_string or 'All'}")
            count = self._fetch_and_save(query, venture_id, category_string, relevance_keywords)
            if count > 0:
                self.logger.info(f"✅ Intel Agent: Saved {count} relevant articles using query: '{query}'")
                return {"status": "success", "summary": f"Found {count} trends for '{query}'."}
            else:
                self.logger.warning(f"⚠️ Intel Agent: No relevant results for '{query}', trying broader query...")

        self.logger.error(f"❌ Intel Agent: All query attempts exhausted with no relevant results.")
        return {"status": "error", "message": "No relevant articles found for any query variant."}

    def _build_query_candidates(self, manual_query, brand_niche):
        """Returns an ordered list of queries from specific to broad.

        1. Core keywords from the manual query (filler words stripped)
        2. Brand niche only (e.g. "Yoga")
        3. Niche + broad wellness term as last resort
        """
        candidates = []

        if manual_query:
            stopwords = {"for", "the", "and", "a", "an", "to", "in", "of", "on", "with", "how"}
            keywords = [w for w in manual_query.split() if w.lower() not in stopwords and len(w) > 2]
            if keywords:
                candidates.append(" ".join(keywords[:3]))

        if brand_niche:
            candidates.append(brand_niche)

        candidates.append(f"{brand_niche} wellness tips")

        return candidates

    def _fetch_and_save(self, query, venture_id, category_string, relevance_keywords):
        """Executes one NewsData query, filters for relevance, saves results.

        Returns count of saved articles.
        """
        try:
            response = self.api.latest_api(
                q=query,
                language="en",
                category=category_string
            )

            if response.get('status') != "success":
                self.logger.error(f"❌ Intel Agent API error: {response.get('message', 'Unknown error')}")
                return 0

            articles = response.get('results', [])
            self.logger.info(f"API returned {len(articles)} articles, filtering for relevance...")

            count = 0
            for article in articles[:10]:  # scan up to 10, save up to 5
                title = article.get('title', '')
                description = article.get('description', '') or ''
                combined = (title + ' ' + description).lower()

                if not any(kw in combined for kw in relevance_keywords):
                    self.logger.info(f"Skipping off-topic: {title[:70]}")
                    continue

                self.logger.info(f"Saving: {title[:80]}")
                self.save_intel(
                    venture_id=venture_id,
                    intel_type="trending_topic",
                    content=title,
                    metadata=article
                )
                count += 1
                if count >= 5:
                    break

            return count

        except Exception as e:
            self.logger.error(f"❌ Intel Agent fetch error: {e}")
            return 0

    def save_intel(self, venture_id, intel_type, content, metadata=None):
        db_pool = self.get_service("db_pool")
        if not db_pool:
            self.logger.warning("⚠️ No DB Pool: Intel not saved.")
            return

        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.market_intel (venture_id, intel_type, content, metadata)
                    VALUES (%s, %s, %s, %s);
                """, (venture_id, intel_type, content, json.dumps(metadata)))
                conn.commit()
                self.logger.info(f"✅ Saved to DB: {content[:60]}")
        except Exception as e:
            self.logger.error(f"⚠️ Intel DB save error: {e}")
        finally:
            db_pool.putconn(conn)