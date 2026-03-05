import os
import json
import requests
from .base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled

class ComposerAgent(BaseAgent):
    """
    Step 4: The Editor.
    Assembles Kling video clips, ElevenLabs audio, and synchronized captions 
    into a final professional video via Creatomate.
    """

    def __init__(self, services=None, provider="creatomate"):
        super().__init__(agent_id="composer", services=services)
        self.contract_name = "composer"
        self.provider = provider
        self.api_url = "https://api.creatomate.com/v1/renders"

    def run(self, input_data, context, campaign_id=None):
        """Standard entry point for the LimesOutpost Orchestrator."""
        if dry_run_enabled():
            return self.dry_run(input_data, context)
        return self.live_run(input_data, context)

    def live_run(self, comp_brief, brand_snapshot):
        """Constructs a multi-scene timeline for the Creatomate API."""
        self.logger.info(f"📡 Composer Agent [LIVE]: Constructing Timeline for {self.provider}...")

        visuals = comp_brief.get("visual_data", {}) 
        audio = comp_brief.get("voiceover_data", {}) 
        
        scenes = visuals.get("scenes", []) 
        audio_url = audio.get("audio_file_path") 
        alignment = audio.get("alignment_data", {}) 

        if not scenes or not audio_url:
            self.logger.warning("⚠️ Composer: Missing critical assets (scenes or audio).")
            return self.dry_run(comp_brief, brand_snapshot)

        subtitles = self._transform_alignment_to_subtitles(alignment) 

        source = {
            "output_format": "mp4",
            "width": 1080,
            "height": 1920,
            "elements": [
                {
                    "type": "audio",
                    "source": audio_url,
                    "duration": audio.get("duration_seconds")
                }
            ]
        }

        current_time = 0
        total_audio_duration = audio.get("duration_seconds", 0)
        scene_duration = total_audio_duration / len(scenes) if scenes else 0
        
        for scene in scenes:
            source["elements"].append({
                "type": "video",
                "source": scene.get("video_file_path"),
                "time": current_time,
                "duration": scene_duration,
                "fit": "cover"
            })
            current_time += scene_duration

        source["elements"].append({
            "type": "text",
            "text": "[caption-placeholder]",
            "subtitles": subtitles,
            "y": "80%",
            "fill_color": "#FFFFFF",
            "background_color": "#000000",
            "font_family": "Montserrat",
            "font_weight": "800",
            "font_size": "64px"
        })

        try:
            api_key = os.getenv("CREATOMATE_API_KEY")
            if not api_key:
                raise Exception("Missing CREATOMATE_API_KEY")

            response = requests.post(
                self.api_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"source": source}
            )
            response.raise_for_status()
            render_result = response.json()[0] 

            return self._build_final_output(render_result, comp_brief)

        except Exception as e:
            self.logger.error(f"❌ COMPOSER API ERROR: {e}")
            return self.dry_run(comp_brief, brand_snapshot)

    def _transform_alignment_to_subtitles(self, alignment_data):
        """Groups ElevenLabs character data into synchronized word-level captions."""
        if not alignment_data or "characters" not in alignment_data:
            return []

        words = []
        current_word = ""
        start_time = None

        chars = alignment_data.get("characters", [])
        start_times = alignment_data.get("character_start_times_seconds", [])
        end_times = alignment_data.get("character_end_times_seconds", [])

        for i in range(len(chars)):
            char = chars[i]
            if char != " " and start_time is None:
                start_time = start_times[i]

            if char != " ":
                current_word += char

            if char == " " or i == len(chars) - 1:
                if current_word:
                    words.append({
                        "text": current_word.upper(), 
                        "time": round(start_time, 3),
                        "duration": round(end_times[i] - start_time, 3)
                    })
                current_word = ""
                start_time = None
        return words

    def _build_final_output(self, render_data, comp_brief):
        """Standardizes output for the Composer Contract."""
        audio_data = comp_brief.get("voiceover_data", {}) 
        duration = audio_data.get("duration_seconds", 0) 
        
        return {
            "status": render_data.get("status", "planned"), 
            "url": render_data.get("url"), 
            "render_id": render_data.get("id") or render_data.get("render_id"), 
            "provider": self.provider, 
            "composition_metadata": {
                "template_id": os.getenv("CREATOMATE_TEMPLATE_ID", "default_yoga_template"), 
                "has_captions": True, 
                "total_duration": duration 
            }
        }

    def dry_run(self, comp_brief, brand_snapshot):
        self.logger.info(f"🧪 Composer Agent [MOCK]: Staging render...")
        mock_res = {"id": "mock_123", "url": "https://example.com/mock_video.mp4", "status": "completed"}
        return self._build_final_output(mock_res, comp_brief)