import json
import os
from .base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled

class ScriptAgent(BaseAgent):
    def __init__(self, services=None):
        super().__init__(agent_id="script", services=services)
        self.contract_name = "script"

    def run(self, input_data, context, campaign_id=None):
        """
        Main entry point for the Orchestrator.
        Maps Strategy output into a structured Script using the agnostic LLM provider.
        """
        brand_snapshot = self.get_brand(context)
        strategy_text = input_data.get("strategy_output", "")
        topic = input_data.get("chosen_topic", "Wellness Flow")

        if dry_run_enabled():
            result = self.dry_run({"strategy": strategy_text, "topic": topic}, brand_snapshot)
        else:
            result = self.live_run({"strategy": strategy_text, "topic": topic}, brand_snapshot)

        if isinstance(result, dict) and result.get("status") == "error":
            return result

        return self.validate_result(result, self.contract_name)

    def live_run(self, strategy_input, brand_snapshot):
        """Agnostic Live Run: Uses self.llm to convert strategy to script."""
        self.logger.info(f"✍️ Script Agent [LIVE]: Drafting categorized script for: {strategy_input['topic']}")

        system_prompt = f"""
        You are an Expert Scriptwriter for {brand_snapshot.get('name', 'a wellness brand')}.
        
        TASK:
        Convert the provided Strategy into a short-form video script (60 seconds).
        You MUST categorize every scene into one of these segment_types: 'hook', 'problem', 'insight', 'cta'.

        RESPONSE FORMAT (Strict JSON):
        {{
            "video_title": "Title",
            "scenes": [
                {{
                    "scene_id": 1,
                    "segment_type": "hook",
                    "visual": "visual description",
                    "audio": "voiceover text"
                }}
            ]
        }}
        """

        user_prompt = f"Strategy: {strategy_input['strategy']}"
        
        raw_response = self.llm.generate(system_prompt, user_prompt)
        
        if raw_response:
            try:
                script_data = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
                return self._build_final_output(script_data, brand_snapshot)
            except Exception as e:
                self.logger.warning(f"⚠️ [SCRIPT ERROR] JSON Parsing failed: {e}. Falling back to dry run.")
        
        return self.dry_run(strategy_input, brand_snapshot)

    def _build_final_output(self, raw_data, brand_snapshot):
        """Maps raw data to the strict system contracts."""
        raw_scenes = raw_data.get("scenes") or []
        
        formatted_scenes = []
        script_segments = []
        voiceover_segments = []

        for scene in raw_scenes:
            audio_text = scene.get("audio", "")
            visual_desc = scene.get("visual") or scene.get("visual_description", "Atmospheric wellness shot")
            
            # 1. Format for VisualAgent (Root 'scenes')
            formatted_scenes.append({
                "scene_id": scene.get("scene_id"),
                "visual_description": visual_desc,
                "voiceover_text": audio_text,
                "duration_weight": round(1.0 / len(raw_scenes), 2) if raw_scenes else 1.0
            })
            
            # 2. Format for VoiceoverAgent (Root 'script_output')
            script_segments.append({
                "segment_type": scene.get("segment_type", "insight"),
                "text": audio_text,
                "visual_cue": visual_desc
            })
            
            if audio_text:
                voiceover_segments.append(audio_text)
        
        full_voiceover = " ".join(voiceover_segments)
        total_word_count = len(full_voiceover.split()) if full_voiceover else 0

        return {
            "status": "success",
            "scenes": formatted_scenes,
            "script_output": script_segments,
            "full_script_text": full_voiceover,
            "total_word_count": total_word_count,
            "metadata": {
                "title": raw_data.get("video_title", "Untitled Video"),
                "full_voiceover": full_voiceover,
                "brand_voice": brand_snapshot.get("narrative", {}).get("tone", "calm"),
                "total_scenes": len(formatted_scenes)
            }
        }

    def dry_run(self, strategy_input, brand_snapshot):
        """Mock output for testing without API calls."""
        self.logger.info(f"🧪 Script Agent [DRY RUN]: Generating mock script for '{strategy_input['topic']}'")
        mock_data = {
            "video_title": f"Mock: {strategy_input['topic']}",
            "scenes": [
                {
                    "scene_id": 1,
                    "segment_type": "hook",
                    "visual": "Calm morning sun through a window.",
                    "audio": f"Morning mobility is the secret to a day like {strategy_input['topic']}."
                },
                {
                    "scene_id": 2,
                    "segment_type": "cta",
                    "visual": "Brand logo fades in.",
                    "audio": "Follow LimesOutpost for your daily dose of Zen."
                }
            ]
        }
        return self._build_final_output(mock_data, brand_snapshot)