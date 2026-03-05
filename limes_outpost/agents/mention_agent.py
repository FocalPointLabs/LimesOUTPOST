import os
import time
import pickle
import requests
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.agents.twitter_publisher_agent import (
    X_MENTIONS_URL, TOKEN_CACHE_TEMPLATE,
)
from limes_outpost.utils.dry_run import dry_run_enabled

X_ME_URL     = "https://api.twitter.com/2/users/me"
MAX_MENTIONS = int(os.getenv("SOCIAL_MAX_MENTIONS", "20"))
SPAM_SIGNALS = ["follow me", "free followers", "click here", "win", "prize", "!!!"]


class MentionAgent(BaseAgent):
    """
    Social Reply Pipeline Step 1: Mention Fetcher + Inline Triager.
    Saves mentions to social_mentions then triages them immediately
    so ReplyAgent can pick them up without a separate triage step.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="mention", services=services)

    def run(self, input_data, context, campaign_id=None):
        if dry_run_enabled():
            return self.dry_run(input_data, context)
        return self.live_run(input_data, context)

    def live_run(self, input_data, context):
        venture_id = self.get_venture_id(context)
        self.logger.info(f"📡 Mention Agent [LIVE]: Fetching mentions for {venture_id}...")

        try:
            token   = self._load_token(venture_id)
            user_id = self._get_user_id(token)
        except Exception as e:
            return {"status": "error", "message": f"X auth failed: {e}"}

        headers = {"Authorization": f"Bearer {token['access_token']}"}
        url     = X_MENTIONS_URL.format(user_id=user_id)
        params  = {
            "max_results":  MAX_MENTIONS,
            "tweet.fields": "conversation_id,in_reply_to_user_id,author_id,created_at",
            "expansions":   "author_id",
            "user.fields":  "username,name",
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data     = response.json()
            mentions = data.get("data", [])
            users    = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

            if not mentions:
                self.logger.info("📭 Mention Agent: No new mentions found.")
                return {"status": "success", "fetched": 0}

            saved = skipped = 0
            for mention in mentions:
                author = users.get(mention.get("author_id"), {})
                if self._save_mention(mention, author, venture_id):
                    saved += 1
                else:
                    skipped += 1

            self.logger.info(f"✅ Mention Agent: Saved {saved}, skipped {skipped}.")
            triaged, ignored = self._triage_fetched_mentions(venture_id, context)
            self.logger.info(f"🔍 Mention Agent: Triaged {triaged}, ignored {ignored}.")
            return {"status": "success", "fetched": saved, "skipped": skipped, "triaged": triaged}

        except Exception as e:
            self.logger.error(f"❌ Mention Agent fetch failed: {e}")
            return {"status": "error", "message": str(e)}

    def dry_run(self, input_data, context):
        venture_id = self.get_venture_id(context)
        self.logger.info(f"🧪 Mention Agent [DRY RUN]: Simulating mention fetch...")

        ts = int(time.time())
        mocks = [
            {
                "mention_id":      f"mock_mention_001_{ts}",
                "author_username": "yogafan123",
                "author_id":       "mock_user_001",
                "text":            "This morning flow changed everything for me 🙏 @YogaZen",
                "conversation_id": f"mock_conv_001_{ts}",
                "in_reply_to_id":  None,
            },
            {
                "mention_id":      f"mock_mention_002_{ts}",
                "author_username": "spamaccount99",
                "author_id":       "mock_user_002",
                "text":            "Follow me for free followers!! @YogaZen",
                "conversation_id": f"mock_conv_002_{ts}",
                "in_reply_to_id":  None,
            },
        ]

        saved = sum(1 for m in mocks if self._save_mention_direct(m, venture_id))
        self.logger.info(f"🧪 Mention Agent [DRY RUN]: Saved {saved} mock mention(s).")

        triaged, ignored = self._triage_fetched_mentions(venture_id, context)
        self.logger.info(f"🧪 Mention Agent [DRY RUN]: Triaged {triaged}, ignored {ignored}.")

        return {"status": "success", "fetched": saved, "skipped": 0, "triaged": triaged}

    def _triage_fetched_mentions(self, venture_id, context):
        mentions  = self._fetch_untriaged(venture_id)
        if not mentions:
            return 0, 0

        whitelist = self._load_whitelist(venture_id)
        triaged = ignored = 0

        for mention in mentions:
            text   = mention.get("text", "").lower()
            author = mention.get("author_username", "").lower()
            is_wl  = author in whitelist
            is_spam = any(s in text for s in SPAM_SIGNALS)

            if is_spam and not is_wl:
                category, priority, notes = "ignore", 1, "Spam detected. No reply needed."
            elif is_wl:
                category, priority, notes = "urgent", 8, "Known contact — prompt reply needed."
            else:
                category, priority, notes = "normal", 5, "Genuine mention worth a warm reply."

            status = "ignored" if category == "ignore" else "triaged"
            self._save_triage(mention["id"], category, priority, is_wl, notes, status)

            if status == "triaged":
                triaged += 1
                self.logger.info(f"✅ Triaged @{mention.get('author_username')} -> {category.upper()} | {priority}/10")
            else:
                ignored += 1
                self.logger.info(f"🗑️  Ignored @{mention.get('author_username')} (spam)")

        return triaged, ignored

    def _save_mention(self, mention, author, venture_id):
        parsed = {
            "mention_id":      mention.get("id"),
            "author_username": author.get("username", ""),
            "author_id":       mention.get("author_id", ""),
            "text":            mention.get("text", ""),
            "conversation_id": mention.get("conversation_id"),
            "in_reply_to_id":  mention.get("in_reply_to_tweet_id"),
        }
        return self._save_mention_direct(parsed, venture_id)

    def _save_mention_direct(self, parsed, venture_id):
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return False
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.social_mentions (
                        venture_id, platform, mention_id,
                        author_username, author_id, text,
                        conversation_id, in_reply_to_id, status
                    ) VALUES (%s, 'twitter', %s, %s, %s, %s, %s, %s, 'fetched')
                    ON CONFLICT (platform, mention_id) DO NOTHING;
                """, (
                    venture_id,
                    parsed["mention_id"],
                    parsed.get("author_username", ""),
                    parsed.get("author_id", ""),
                    parsed.get("text", ""),
                    parsed.get("conversation_id"),
                    parsed.get("in_reply_to_id"),
                ))
                inserted = cur.rowcount > 0
                conn.commit()
                return inserted
        except Exception as e:
            self.logger.warning(f"⚠️ [Mention] DB save failed: {e}")
            return False
        finally:
            db_pool.putconn(conn)

    def _fetch_untriaged(self, venture_id):
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return []
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, venture_id, mention_id,
                           author_username, author_id, text,
                           conversation_id, in_reply_to_id
                    FROM public.social_mentions
                    WHERE venture_id = %s AND status = 'fetched'
                    ORDER BY created_at ASC;
                """, (venture_id,))
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            db_pool.putconn(conn)

    def _save_triage(self, mention_id, category, priority_score,
                     is_whitelisted, triage_notes, status):
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE public.social_mentions SET
                        category       = %s,
                        priority_score = %s,
                        is_whitelisted = %s,
                        triage_notes   = %s,
                        status         = %s,
                        updated_at     = NOW()
                    WHERE id = %s;
                """, (category, priority_score, is_whitelisted,
                      triage_notes, status, str(mention_id)))
                conn.commit()
        finally:
            db_pool.putconn(conn)

    def _load_whitelist(self, venture_id):
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return set()
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT whitelisted_emails FROM public.ventures WHERE id = %s",
                    (venture_id,)
                )
                row = cur.fetchone()
                return {e.lower() for e in row[0]} if row and row[0] else set()
        finally:
            db_pool.putconn(conn)

    def _load_token(self, venture_id):
        token_path = TOKEN_CACHE_TEMPLATE.format(venture_id=venture_id)
        if not os.path.exists(token_path):
            raise FileNotFoundError(f"No X token for venture '{venture_id}'.")
        with open(token_path, "rb") as f:
            return pickle.load(f)

    def _get_user_id(self, token):
        headers  = {"Authorization": f"Bearer {token['access_token']}"}
        response = requests.get(X_ME_URL, headers=headers)
        response.raise_for_status()
        return response.json()["data"]["id"]