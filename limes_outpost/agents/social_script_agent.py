import json
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled

# Hard X character limit — enforced at contract level too
X_CHAR_LIMIT = 280


class SocialScriptAgent(BaseAgent):
    """
    Social Pipeline Step 2: The Social Scriptwriter.

    Receives the trend_sniper_output and produces platform-ready
    tweet copy: hook, body, hashtags, and optional CTA — all within
    X's 280 character limit.

    Brand vocabulary rules are enforced via the system prompt.
    The contract enforces the character limit as a hard schema rule.

    Output is inserted directly into publish_queue (platform='twitter')
    by the Archivist — no file is produced, no asset row is written.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="social_script", services=services)
        self.contract_name = "social_script"

    def run(self, input_data, context, campaign_id=None):
        brand = self.get_brand(context)

        # Unwrap trend_sniper_output envelope if present
        sniper_data = self.unwrap_input(input_data, "trend_sniper_output") \
                      if isinstance(input_data, dict) and "trend_sniper_output" in input_data \
                      else input_data

        if not sniper_data or not isinstance(sniper_data, dict):
            return {"status": "error", "message": "SocialScriptAgent requires trend_sniper_output."}

        if dry_run_enabled():
            result = self.dry_run(sniper_data, brand)
        else:
            result = self.live_run(sniper_data, brand)

        if isinstance(result, dict) and result.get("status") == "error":
            return result

        return self.validate_result(result, self.contract_name)

    # ------------------------------------------------------------------
    # Live run
    # ------------------------------------------------------------------

    def live_run(self, sniper_data, brand):
        niche         = brand.get("niche", "Wellness")
        rules         = brand.get("rules", {})
        narrative     = brand.get("narrative", {})
        cta_phrasing  = narrative.get("cta_phrasing", "Follow for more.")
        approved_vocab = rules.get("approved_vocabulary", [])
        banned_vocab   = rules.get("banned_vocabulary", [])

        viral_angle      = sniper_data.get("viral_angle", "")
        topic            = sniper_data.get("topic", "")
        emotional_trigger = sniper_data.get("emotional_trigger", "curiosity")
        hook_format      = sniper_data.get("hook_format", "statement")

        system_prompt = f"""
You are a social media copywriter for a {niche} brand on X (Twitter).

Your job is to write a single tweet (max {X_CHAR_LIMIT} characters TOTAL including hashtags).

BRAND RULES:
- APPROVED vocabulary to use naturally: {', '.join(approved_vocab)}
- BANNED vocabulary — never use: {', '.join(banned_vocab)}
- CTA style: {cta_phrasing}

TWEET PRINCIPLES:
- Hook format: {hook_format} — the first line must stop the scroll
- Emotional trigger to activate: {emotional_trigger}
- No corporate speak, no clichés
- Hashtags: 2-3 max, relevant, placed at the end
- The ENTIRE tweet including hashtags must be {X_CHAR_LIMIT} characters or fewer
- Count carefully — this is a hard limit

RESPONSE FORMAT — return valid JSON only, no preamble:
{{
    "tweet_text": "The complete ready-to-post tweet including hashtags",
    "char_count": <exact integer character count of tweet_text>,
    "hashtags": ["tag1", "tag2"],
    "hook": "just the opening line isolated for review"
}}
"""

        user_prompt = (
            f"Write a tweet for this viral angle:\n\n"
            f"TOPIC: {topic}\n"
            f"ANGLE: {viral_angle}\n"
            f"WHY IT WORKS: {sniper_data.get('why_it_works', '')}"
        )

        self.logger.info(f"✍️  Social Script [LIVE]: Writing tweet for '{topic[:50]}'...")
        raw = self.llm.generate(system_prompt, user_prompt)

        try:
            result = json.loads(raw) if isinstance(raw, str) else raw
            return self._build_output(result, sniper_data, brand)
        except Exception as e:
            self.logger.warning(f"⚠️ [SocialScript] Parse failed: {e}. Falling back.")
            return self.dry_run(sniper_data, brand)

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    def dry_run(self, sniper_data, brand):
        self.logger.info("🧪 Social Script [DRY RUN]: Generating mock tweet...")
        niche       = brand.get("niche", "Wellness")
        viral_angle = sniper_data.get("viral_angle", f"The truth about {niche.lower()}")

        # Keep mock well under limit
        mock_tweet = (
            f"Most people overthink {niche.lower()}.\n\n"
            f"{viral_angle[:100]}.\n\n"
            f"Start simple. Stay consistent.\n\n"
            f"#{niche.replace(' ', '')} #Wellness #MindBody"
        )[:X_CHAR_LIMIT]

        mock = {
            "tweet_text": mock_tweet,
            "char_count": len(mock_tweet),
            "hashtags":   [niche.replace(" ", ""), "Wellness", "MindBody"],
            "hook":       f"Most people overthink {niche.lower()}."
        }
        return self._build_output(mock, sniper_data, brand)

    # ------------------------------------------------------------------
    # Output builder
    # ------------------------------------------------------------------

    def _build_output(self, raw, sniper_data, brand):
        tweet_text = raw.get("tweet_text", "")

        # Hard truncation safety net — contract will also catch this
        if len(tweet_text) > X_CHAR_LIMIT:
            self.logger.warning(
                f"⚠️ [SocialScript] Tweet exceeded {X_CHAR_LIMIT} chars "
                f"({len(tweet_text)}). Truncating."
            )
            tweet_text = tweet_text[:X_CHAR_LIMIT]

        return {
            "status":            "success",
            "venture_id":        brand.get("venture_id", "unknown"),
            "niche_focus":       brand.get("niche", "General"),
            "topic":             sniper_data.get("topic", ""),
            "viral_angle":       sniper_data.get("viral_angle", ""),
            "emotional_trigger": sniper_data.get("emotional_trigger", "curiosity"),
            "hook_format":       sniper_data.get("hook_format", "statement"),  # add this
            "tweet_text":        tweet_text,
            "char_count":        len(tweet_text),
            "hashtags":          raw.get("hashtags", []),
            "hook":              raw.get("hook", ""),
        }