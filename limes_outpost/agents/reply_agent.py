import json
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled

X_REPLY_LIMIT = 280


class ReplyAgent(BaseAgent):
    """
    Social Reply Pipeline Step 2: The Reply Drafter.

    Reads triaged mentions and generates on-brand reply drafts.
    Replies are grounded in the brand's tone vocabulary and rules —
    same pattern as DraftAgent but with character limit constraints
    and social platform voice calibration.

    Each draft inserted into publish_queue (platform='twitter')
    with reply_to_tweet_id stored in tags metadata.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="reply", services=services)
        self.contract_name = "social_reply"

    def run(self, input_data, context, campaign_id=None):
        venture_id = self.get_venture_id(context)
        whitelist  = self._load_whitelist(venture_id)
        mentions   = self._fetch_triaged_mentions(venture_id)

        if not mentions:
            self.logger.info("📭 Reply Agent: No triaged mentions to draft.")
            return {"status": "success", "drafted": 0}

        self.logger.info(f"✍️  Reply Agent: Drafting replies for {len(mentions)} mention(s)...")

        drafted = 0
        for mention in mentions:
            draft = self._generate_reply(mention, context, whitelist)
            if not draft:
                continue

            try:
                validated = self.validate_result(draft, self.contract_name)
            except Exception as e:
                self.logger.warning(
                    f"⚠️ [Reply] Contract breach for mention "
                    f"'{mention.get('mention_id')}': {e}. Skipping."
                )
                continue

            enqueued = self._enqueue_reply(mention, validated, venture_id)
            if enqueued:
                self._mark_drafted(mention["id"])
                drafted += 1
                self.logger.info(
                    f"💬 Reply drafted for @{mention.get('author_username', '?')}: "
                    f"'{validated['reply_text'][:60]}...'"
                )

        return {"status": "success", "drafted": drafted}

    # ------------------------------------------------------------------
    # Reply generation
    # ------------------------------------------------------------------

    def _generate_reply(self, mention, context, whitelist):
        brand          = self.get_brand(context)
        niche          = brand.get("niche", "Wellness")
        rules          = brand.get("rules", {})
        identity       = brand.get("identity", {})
        tone_vocab     = identity.get("tone_vocabulary", [])
        approved_vocab = rules.get("approved_vocabulary", [])
        banned_vocab   = rules.get("banned_vocabulary", [])
        brand_name     = brand.get("name", "")

        author          = mention.get("author_username", "someone")
        mention_text    = mention.get("text", "")
        category        = mention.get("category", "normal")
        is_whitelisted  = mention.get("is_whitelisted", False)
        triage_notes    = mention.get("triage_notes", "")

        warmth = (
            "This is a known follower or partner — be warm and personal."
            if is_whitelisted
            else "This is a general follower — be genuine, friendly, and on-brand."
        )

        system_prompt = f"""
You are the social media voice for {brand_name}, a {niche} brand on X (Twitter).

BRAND TONE: {', '.join(tone_vocab)}
APPROVED vocabulary: {', '.join(approved_vocab)}
BANNED vocabulary — never use: {', '.join(banned_vocab)}

REPLY RULES:
- {warmth}
- Max {X_REPLY_LIMIT} characters TOTAL — count carefully, this is a hard limit
- Sound human, not corporate — no "Great question!" or "Thanks for sharing!"
- Start with @{author} only if it feels natural, not required
- Match the energy of the original mention
- No hashtags in replies unless they add real value

TRIAGE CONTEXT:
{triage_notes}

RESPONSE FORMAT — return valid JSON only, no preamble:
{{
    "reply_text": "The complete reply, max {X_REPLY_LIMIT} chars",
    "char_count": <exact integer>
}}
"""

        user_prompt = f"Draft a reply to this mention:\n\n@{author}: {mention_text}"

        if dry_run_enabled():
            return self._mock_reply(mention, brand)

        raw = self.llm.generate(system_prompt, user_prompt)

        try:
            result = json.loads(raw) if isinstance(raw, str) else raw
            return self._build_output(result, mention)
        except Exception as e:
            self.logger.warning(f"⚠️ [Reply] Parse failed: {e}. Using fallback.")
            return self._mock_reply(mention, brand)

    def _mock_reply(self, mention, brand):
        author    = mention.get("author_username", "there")
        niche     = brand.get("niche", "wellness")
        tone      = brand.get("identity", {}).get("tone_vocabulary", ["grounded"])

        reply = f"This means a lot 🙏 Keep showing up for your practice — that's everything. #{niche.replace(' ', '')}"
        reply = reply[:X_REPLY_LIMIT]

        return self._build_output(
            {"reply_text": reply, "char_count": len(reply)},
            mention
        )

    def _build_output(self, raw, mention):
        reply_text = raw.get("reply_text", "")

        if len(reply_text) > X_REPLY_LIMIT:
            self.logger.warning(
                f"⚠️ [Reply] Reply exceeded {X_REPLY_LIMIT} chars. Truncating."
            )
            reply_text = reply_text[:X_REPLY_LIMIT]

        return {
            "reply_text":  reply_text,
            "char_count":  len(reply_text),
        }

    # ------------------------------------------------------------------
    # Queue insertion
    # ------------------------------------------------------------------

    def _enqueue_reply(self, mention, draft, venture_id):
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return False

        social_meta = json.dumps({
            "reply_to_tweet_id": mention.get("mention_id"),
            "author_username":   mention.get("author_username", ""),
            "author_id":         mention.get("author_id", ""),
            "original_text":     mention.get("text", "")[:200],
            "category":          mention.get("category", "normal"),
            "priority_score":    mention.get("priority_score", 5),
            "is_whitelisted":    mention.get("is_whitelisted", False),
        })

        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.publish_queue
                        (venture_id, platform, status, title, description, tags)
                    VALUES (
                        %s, 'twitter', 'pending_review',
                        %s, %s, %s
                    );
                """, (
                    venture_id,
                    f"Reply to @{mention.get('author_username', 'unknown')}",
                    draft["reply_text"],
                    [social_meta],
                ))
                conn.commit()
                return True
        except Exception as e:
            self.logger.warning(f"⚠️ [Reply] Failed to enqueue: {e}")
            return False
        finally:
            db_pool.putconn(conn)

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _fetch_triaged_mentions(self, venture_id):
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return []
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        id, venture_id, platform, mention_id,
                        author_username, author_id, text,
                        conversation_id, in_reply_to_id,
                        category, priority_score, is_whitelisted, triage_notes
                    FROM public.social_mentions
                    WHERE venture_id = %s AND status = 'triaged'
                    ORDER BY priority_score DESC, created_at ASC;
                """, (venture_id,))
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
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
                if row and row[0]:
                    return {e.lower() for e in row[0]}
                return set()
        finally:
            db_pool.putconn(conn)

    def _mark_drafted(self, mention_id):
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE public.social_mentions
                    SET status = 'drafted', updated_at = NOW()
                    WHERE id = %s;
                """, (str(mention_id),))
                conn.commit()
        finally:
            db_pool.putconn(conn)