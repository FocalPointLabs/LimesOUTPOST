import json
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled


class BlogStrategyAgent(BaseAgent):
    """
    Blog Pipeline Step 1: The Strategist.

    Consumes the shared intel_directive from IntelStrategyAgent and produces
    a fully-formed blog brief: headline, SEO keyword, structure plan, and
    angle — all grounded in the venture's brand profile.

    SEO strategy lives here (not in the brand profile) because it's a
    tactical production decision, not brand identity.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="blog_strategy", services=services)
        self.contract_name = "blog_strategy"

    def run(self, input_data, context, campaign_id=None):
        brand_snapshot = self.get_brand(context)

        # --- Resolve topic from intel_directive ---
        # input_data is the full intel_directive output from IntelStrategyAgent.
        # We prefer inspiration_source (the raw headline) over production_prompt
        # because production_prompt is video-framed language.
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
            niche = brand_snapshot.get("niche") or "Wellness"
            topic = f"Latest trends in {niche}"

        if dry_run_enabled():
            result = self.dry_run(topic, brand_snapshot)
        else:
            result = self.live_run(topic, brand_snapshot)

        envelope = {
            "status": "success",
            "chosen_topic": topic,
            "blog_strategy_output": result,
            "directive_used": isinstance(input_data, dict)
        }
        return self.validate_result(envelope, self.contract_name)

    def live_run(self, topic, brand_snapshot):
        blog_config = brand_snapshot.get("blog", {})
        style = blog_config.get("style", {})
        structure = blog_config.get("structure", {})
        audience = brand_snapshot.get("audience", {})
        rules = blog_config.get("rules", {})

        system_prompt = f"""
You are a world-class content strategist and SEO specialist for {brand_snapshot.get('name', 'a wellness brand')}.

BRAND NICHE: {brand_snapshot.get('niche', 'General')}
AUTHOR PERSONA: {blog_config.get('author_persona', 'A knowledgeable, approachable guide.')}
AUDIENCE ASPIRATIONS: {', '.join(audience.get('core_aspirations', []))}
AUDIENCE BELIEFS: {', '.join(audience.get('core_beliefs', []))}
NARRATIVE FRAMEWORK: {structure.get('framework', 'Hook-Context-Insight-Takeaway-CTA')}
INTRO STYLE: {structure.get('intro_style', 'open_with_question')}
TONE: {style.get('tone', 'conversational-authoritative')}
TARGET LENGTH: ~{style.get('avg_article_length_words', 800)} words
BANNED WORDS: {', '.join(rules.get('banned_vocabulary', []))}

TASK:
Given the trending topic below, produce a complete blog article brief.

SEO STRATEGY RULES:
- Choose one specific long-tail keyword (3-5 words) that a beginner would realistically search
- The keyword must appear naturally in the headline
- Meta description must be under 155 characters and include the keyword
- Suggest 2-3 semantically related secondary keywords

RESPONSE FORMAT — return valid JSON only, no preamble:
{{
    "headline": "Article headline (must contain the primary keyword naturally)",
    "primary_keyword": "the exact long-tail keyword",
    "secondary_keywords": ["keyword 2", "keyword 3"],
    "meta_description": "Under 155 chars, includes primary keyword",
    "angle": "The specific perspective or argument this article takes",
    "hook_sentence": "Opening sentence — must match intro_style: {structure.get('intro_style', 'open_with_question')}",
    "section_plan": [
        {{"heading": "Section heading", "key_point": "What this section establishes"}}
    ],
    "cta": "{structure.get('cta_phrasing', 'Follow for more.')}",
    "estimated_word_count": {style.get('avg_article_length_words', 800)}
}}
"""

        user_prompt = f"Create a blog strategy brief for this trending topic: {topic}"

        self.logger.info(f"🧠 Blog Strategy Agent [LIVE]: Building brief for '{topic}'...")
        raw_response = self.llm.generate(system_prompt, user_prompt)

        if raw_response:
            try:
                output_data = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
                return self._build_final_output(output_data, brand_snapshot)
            except Exception as e:
                self.logger.warning(f"⚠️ [BLOG STRATEGY ERROR] JSON parse failed: {e}. Falling back to dry run.")

        return self.dry_run(topic, brand_snapshot)

    def dry_run(self, topic, brand_snapshot):
        self.logger.info(f"🧪 Blog Strategy Agent [DRY RUN]: Generating mock brief for '{topic}'...")
        blog_config = brand_snapshot.get("blog", {})
        structure = blog_config.get("structure", {})
        style = blog_config.get("style", {})

        mock_raw = {
            "headline": f"How {topic} Can Transform Your Morning Yoga Practice",
            "primary_keyword": f"{topic} yoga benefits",
            "secondary_keywords": [f"{topic} for beginners", "morning yoga routine"],
            "meta_description": f"Discover how {topic[:60]} can deepen your yoga practice. Tips for all levels.",
            "angle": f"Reframe {topic} as a mindfulness opportunity rather than a challenge.",
            "hook_sentence": f"What if {topic} was the missing piece in your morning practice?",
            "section_plan": [
                {"heading": f"Why {topic} Matters for Yogis", "key_point": "Establish relevance to the audience"},
                {"heading": "How to Incorporate It Into Your Flow", "key_point": "Practical, actionable guidance"},
                {"heading": "A Simple Practice to Try Today", "key_point": "Concrete takeaway they can act on now"}
            ],
            "cta": structure.get("cta_phrasing", "Save this for your next practice. Follow for daily flow."),
            "estimated_word_count": style.get("avg_article_length_words", 800)
        }
        return self._build_final_output(mock_raw, brand_snapshot)

    def _build_final_output(self, raw_data, brand_snapshot):
        """Maps LLM output to the exact keys required by the blog_strategy contract."""
        blog_config = brand_snapshot.get("blog", {})
        style = blog_config.get("style", {})

        return {
            "venture_id": brand_snapshot.get("venture_id", "unknown_venture"),
            "niche_focus": brand_snapshot.get("niche", "General"),
            "headline": raw_data.get("headline", "Untitled Article"),
            "primary_keyword": raw_data.get("primary_keyword", ""),
            "secondary_keywords": raw_data.get("secondary_keywords", []),
            "meta_description": raw_data.get("meta_description", ""),
            "angle": raw_data.get("angle", ""),
            "hook_sentence": raw_data.get("hook_sentence", ""),
            "section_plan": raw_data.get("section_plan", []),
            "cta": raw_data.get("cta", ""),
            "estimated_word_count": raw_data.get(
                "estimated_word_count",
                style.get("avg_article_length_words", 800)
            ),
            "style_config": style  # passed through so BlogWriterAgent doesn't need to re-read brand profile
        }