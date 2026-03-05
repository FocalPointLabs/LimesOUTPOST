import json
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled


class TrendSniperAgent(BaseAgent):
    """
    Social Pipeline Step 1: The Trend Sniper.

    Consumes the shared intel_directive from IntelStrategyAgent and
    reframes it through a social/viral lens — identifying the sharpest
    angle, hook format, and emotional trigger for a tweet.

    This is a thin transformation layer on top of intelligence that
    already exists. The heavy lifting (trend identification, topic
    selection, deduplication) is done upstream by IntelAgent +
    IntelStrategyAgent. This agent's job is purely reframing:
    "what's the most viral way to say this on X?"

    Output feeds directly into SocialScriptAgent.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="trend_sniper", services=services)
        self.contract_name = "trend_sniper"

    def run(self, input_data, context, campaign_id=None):
        brand = self.get_brand(context)

        # Resolve topic from intel_directive — same pattern as BlogStrategyAgent
        topic = ""
        if isinstance(input_data, dict):
            directive = input_data.get("directive", {})
            topic = (
                directive.get("inspiration_source") or
                directive.get("production_prompt") or
                input_data.get("inspiration_source") or
                input_data.get("manual_query")
            )

        if not topic:
            niche = brand.get("niche", "Wellness")
            topic = f"Latest trends in {niche}"

        if dry_run_enabled():
            result = self.dry_run(topic, brand)
        else:
            result = self.live_run(topic, brand)

        return self.validate_result(result, self.contract_name)

    # ------------------------------------------------------------------
    # Live run
    # ------------------------------------------------------------------

    def live_run(self, topic, brand):
        niche          = brand.get("niche", "Wellness")
        tone_vocab     = brand.get("identity", {}).get("tone_vocabulary", [])
        narrative      = brand.get("narrative", {})
        hook_style     = narrative.get("hook_style", "inviting_question")

        system_prompt = f"""
You are a viral social media strategist specializing in {niche} content on X (Twitter).

Your job is to identify the sharpest, most engaging angle for a tweet based on a trending topic.

BRAND TONE: {', '.join(tone_vocab)}
HOOK STYLE: {hook_style}

VIRAL ANGLE PRINCIPLES:
- Find the counterintuitive or surprising take — not the obvious one
- Identify the emotional trigger: curiosity, validation, aspiration, or controversy (light)
- The angle should make someone stop scrolling
- Keep it grounded in {niche} — don't chase virality at the cost of brand alignment

RESPONSE FORMAT — return valid JSON only, no preamble:
{{
    "topic": "the original topic",
    "viral_angle": "the specific reframe or counterintuitive take",
    "emotional_trigger": "curiosity|validation|aspiration|controversy",
    "hook_format": "question|statement|list|hot_take",
    "why_it_works": "1 sentence explaining the psychological appeal"
}}
"""
        user_prompt = f"Find the viral angle for this trending topic: {topic}"

        self.logger.info(f"🎯 Trend Sniper [LIVE]: Finding viral angle for '{topic[:60]}'...")
        raw = self.llm.generate(system_prompt, user_prompt)

        try:
            result = json.loads(raw) if isinstance(raw, str) else raw
            return self._build_output(result, topic, brand)
        except Exception as e:
            self.logger.warning(f"⚠️ [TrendSniper] Parse failed: {e}. Falling back.")
            return self.dry_run(topic, brand)

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    def dry_run(self, topic, brand):
        self.logger.info(f"🧪 Trend Sniper [DRY RUN]: Generating mock angle for '{topic[:60]}'...")
        niche = brand.get("niche", "Wellness")

        mock = {
            "topic":             topic,
            "viral_angle":       f"Most people approach {niche.lower()} wrong — here's the overlooked truth",
            "emotional_trigger": "curiosity",
            "hook_format":       "hot_take",
            "why_it_works":      "Challenges a common assumption, triggering the need to read on."
        }
        return self._build_output(mock, topic, brand)

    # ------------------------------------------------------------------
    # Output builder
    # ------------------------------------------------------------------

    def _build_output(self, raw, topic, brand):
        return {
            "status":           "success",
            "venture_id":       brand.get("venture_id", "unknown"),
            "niche_focus":      brand.get("niche", "General"),
            "topic":            topic,
            "viral_angle":      raw.get("viral_angle", ""),
            "emotional_trigger":raw.get("emotional_trigger", "curiosity"),
            "hook_format":      raw.get("hook_format", "statement"),
            "why_it_works":     raw.get("why_it_works", ""),
        }