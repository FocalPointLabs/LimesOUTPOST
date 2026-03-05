import json
import os
from .base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled

class StrategyAgent(BaseAgent):
    def __init__(self, services=None):
        super().__init__(agent_id="strategy", services=services)
        self.contract_name = "strategy"

    def _build_final_output(self, raw_data, brand_snapshot):
        """Maps raw data to the exact keys required by strategy.json contract."""
        duration_prefs = brand_snapshot.get("narrative", {}).get("target_video_duration_seconds", {})
        default_duration = duration_prefs.get("min", 15)

        return {
            "venture_id": brand_snapshot.get("venture_id", "unknown_venture"),
            "niche_focus": brand_snapshot.get("niche", "General Content"),
            "campaign_name": raw_data.get("campaign_goal") or raw_data.get("campaign_name") or "New Campaign",
            "core_hook": raw_data.get("hook_angle") or raw_data.get("core_hook") or "Unlock your potential today.",
            "target_audience": raw_data.get("target_audience") or "General Audience",
            "estimated_duration_seconds": int(default_duration),
            "content_plan": raw_data.get("content_plan") or raw_data.get("key_takeaways") or []
        }

    def run(self, input_data, context, campaign_id=None):
        """
        Handles both raw string input and dictionary directives.
        Ensures niche_input is never None by searching the entire input dictionary.
        """
        # 1. Use base helper for brand snapshot consistency
        brand_snapshot = self.get_brand(context)
        
        niche_input = ""
        
        # 2. Capture the Directive or the Raw Topic
        if isinstance(input_data, dict):
            directive = input_data.get("directive", {})
            niche_input = (
                input_data.get("production_prompt") or 
                directive.get("production_prompt") or 
                input_data.get("manual_query") or 
                directive.get("manual_query") or
                input_data.get("initial_query") or
                directive.get("initial_query")
            )
        else:
            niche_input = input_data

        # 3. Safety Fallback: Use the brand's actual niche if available
        if not niche_input:
            brand_niche = brand_snapshot.get('niche') or brand_snapshot.get('category') or 'Wellness'
            niche_input = f"Latest trends in {brand_niche}"

        # 4. Execution (Dry vs Live)
        if dry_run_enabled():
            strategy_result = self.dry_run(niche_input, brand_snapshot)
        else:
            strategy_result = self.live_run(niche_input, brand_snapshot)

        result = {
            "status": "success",
            "chosen_topic": niche_input, 
            "strategy_output": strategy_result,
            "directive_used": isinstance(input_data, dict)
        }

        # 5. Validate result against contract before exit
        return self.validate_result(result, self.contract_name)

    def dry_run(self, niche_input, brand_snapshot):
        """Provides mock data for testing without API costs."""
        self.logger.info(f"🧪 Strategy Agent [MOCK]: Generating plan for '{niche_input}'")
        
        mock_raw = {
            "campaign_goal": f"Mastering {niche_input}",
            "hook_angle": f"The one thing you're missing in your {niche_input} routine.",
            "content_plan": [{"sequence_number": 1, "topic": niche_input}]
        }
        return self._build_final_output(mock_raw, brand_snapshot)

    def live_run(self, niche_input, brand_snapshot):
        """Executes live inference using the Cerebras-powered LLMClient."""
        system_prompt = f"""
        You are a World-Class Content Strategist for {brand_snapshot.get('name', 'a premium brand')}.
        
        BRAND MISSION: {brand_snapshot.get('mission', 'Excellence')}
        TARGET AUDIENCE: {brand_snapshot.get('target_audience', 'General')}
        TONE: {brand_snapshot.get('narrative', {}).get('tone', 'Professional')}

        TASK:
        Create a high-impact short-form video strategy for: "{niche_input}"

        RESPONSE FORMAT:
        You must return a valid JSON object with these exact keys:
        {{
            "campaign_goal": "A short, catchy name for this project",
            "hook_angle": "A high-retention opening line (must be >10 characters)",
            "target_audience": "Specific sub-niche for this video",
            "content_plan": ["Key takeaway 1", "Key takeaway 2", "Key takeaway 3"]
        }}
        """

        user_prompt = f"Generate a viral video strategy for: {niche_input}"

        self.logger.info(f"🧠 Strategy Agent [LIVE]: Requesting Cerebras inference for '{niche_input}'...")
        
        raw_response = self.llm.generate(system_prompt, user_prompt)

        if raw_response:
            try:
                output_data = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
                return self._build_final_output(output_data, brand_snapshot)
            except Exception as e:
                self.logger.warning(f"⚠️ [STRATEGY ERROR] JSON Parsing failed: {e}. Falling back to dry run.")
        
        return self.dry_run(niche_input, brand_snapshot)