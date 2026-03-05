import json
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled


class BlogWriterAgent(BaseAgent):
    """
    Blog Pipeline Step 2: The Writer.

    Receives the blog_strategy_output brief and produces a full article draft.
    Brand voice, structure, and vocabulary rules are all enforced via the
    system prompt — the LLM does the writing, the brand profile does the
    guardrailing.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="blog_writer", services=services)
        self.contract_name = "blog_writer"

    def run(self, input_data, context, campaign_id=None):
        brand_snapshot = self.get_brand(context)

        if not input_data or not isinstance(input_data, dict):
            return {"status": "error", "message": "BlogWriterAgent requires a blog_strategy_output dict as input."}

        brief = self.unwrap_input(input_data, "blog_strategy_output")

        if dry_run_enabled():
            result = self.dry_run(brief, brand_snapshot)
        else:
            result = self.live_run(brief, brand_snapshot)

        if isinstance(result, dict) and result.get("status") == "error":
            return result

        return self.validate_result(result, self.contract_name)

    def live_run(self, brief, brand_snapshot):
        blog_config = brand_snapshot.get("blog", {})
        style = brief.get("style_config") or blog_config.get("style", {})
        rules = blog_config.get("rules", {})
        audience = brand_snapshot.get("audience", {})

        section_plan_text = "\n".join([
            f"  {i+1}. {s.get('heading', '')} — {s.get('key_point', '')}"
            for i, s in enumerate(brief.get("section_plan", []))
        ])

        use_subheadings = style.get("use_subheadings", True)
        use_bullets = style.get("use_bullet_points", False)
        pov = style.get("pov", "second_person")
        reading_level = style.get("reading_level", "accessible")
        max_intro_sentences = rules.get("max_intro_sentences", 3)

        system_prompt = f"""
You are the author of {brand_snapshot.get('name', 'a wellness publication')}.

AUTHOR PERSONA:
{blog_config.get('author_persona', 'A knowledgeable, warm, and grounded wellness guide.')}

AUDIENCE:
- Core aspirations: {', '.join(audience.get('core_aspirations', []))}
- Core beliefs: {', '.join(audience.get('core_beliefs', []))}

WRITING RULES — follow these exactly:
- Point of view: {pov.replace('_', ' ')}
- Reading level: {reading_level}
- Use subheadings: {use_subheadings}
- Use bullet points: {use_bullets} (if False, write in prose only)
- Introduction: maximum {max_intro_sentences} sentences before the first subheading
- Target length: ~{brief.get('estimated_word_count', 800)} words
- APPROVED vocabulary to use naturally: {', '.join(rules.get('approved_vocabulary', []))}
- BANNED vocabulary — never use these words: {', '.join(rules.get('banned_vocabulary', []))}

SEO RULES:
- Primary keyword "{brief.get('primary_keyword', '')}" must appear in: the first paragraph, at least one subheading, and the conclusion
- Secondary keywords {brief.get('secondary_keywords', [])} should appear naturally 1-2 times each
- Do not keyword-stuff — if it doesn't read naturally, omit it

ARTICLE STRUCTURE TO FOLLOW:
{section_plan_text}

END WITH:
{brief.get('cta', '')}

RESPONSE FORMAT — return valid JSON only, no preamble:
{{
    "title": "Final article headline",
    "body_markdown": "The full article in markdown. Use ## for subheadings.",
    "word_count": estimated integer word count,
    "primary_keyword_used": true/false,
    "cta_included": true/false
}}
"""

        user_prompt = f"""Write the full article using this brief:

HEADLINE: {brief.get('headline')}
ANGLE: {brief.get('angle')}
OPENING LINE: {brief.get('hook_sentence')}
PRIMARY KEYWORD: {brief.get('primary_keyword')}
"""

        self.logger.info(f"✍️  Blog Writer Agent [LIVE]: Writing '{brief.get('headline', 'article')}'...")
        raw_response = self.llm.generate(system_prompt, user_prompt)

        if raw_response:
            try:
                output_data = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
                return self._build_final_output(output_data, brief, brand_snapshot)
            except Exception as e:
                self.logger.warning(f"⚠️ [BLOG WRITER ERROR] JSON parse failed: {e}. Falling back to dry run.")

        return self.dry_run(brief, brand_snapshot)

    def dry_run(self, brief, brand_snapshot):
        self.logger.info(f"🧪 Blog Writer Agent [DRY RUN]: Generating mock article for '{brief.get('headline', 'article')}'...")

        headline = brief.get("headline", "Mock Article Headline")
        keyword = brief.get("primary_keyword", "yoga benefits")
        hook = brief.get("hook_sentence", "What if your morning practice could change everything?")
        cta = brief.get("cta", "Save this for your next practice. Follow for daily flow.")

        sections = brief.get("section_plan", [
            {"heading": "Section One", "key_point": "Opening context"},
            {"heading": "Section Two", "key_point": "Core insight"},
            {"heading": "Section Three", "key_point": "Practical takeaway"},
        ])

        section_text = "\n\n".join([
            f"## {s.get('heading', 'Section')}\n\nThis section covers {s.get('key_point', 'the key point')}. "
            f"When you bring {keyword} into your practice, you begin to notice a shift — "
            f"not just in your body, but in your presence."
            for s in sections
        ])

        mock_body = f"""{hook}

{section_text}

{cta}"""

        mock_raw = {
            "title": headline,
            "body_markdown": mock_body,
            "word_count": len(mock_body.split()),
            "primary_keyword_used": True,
            "cta_included": True
        }
        return self._build_final_output(mock_raw, brief, brand_snapshot)

    def _build_final_output(self, raw_data, brief, brand_snapshot):
        """Maps LLM output to the exact keys required by the blog_writer contract."""
        return {
            "status": "success",
            "venture_id": brand_snapshot.get("venture_id", "unknown_venture"),
            "title": raw_data.get("title") or brief.get("headline", "Untitled"),
            "body_markdown": raw_data.get("body_markdown", ""),
            "word_count": raw_data.get("word_count", 0),
            "primary_keyword": brief.get("primary_keyword", ""),
            "meta_description": brief.get("meta_description", ""),
            "primary_keyword_used": raw_data.get("primary_keyword_used", False),
            "cta_included": raw_data.get("cta_included", False),
        }