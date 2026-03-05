import base64
import os
import requests
import time
import re
from .base_agent import BaseAgent
# Added from snippet
from limes_outpost.utils.dry_run import dry_run_enabled

class VoiceoverAgent(BaseAgent):
    """
    Step 3: The Narrator.
    Converts script segments into high-fidelity audio via ElevenLabs.
    Receives a list of segment dicts from _map_inputs (extract_key: "script_output").
    """

    def __init__(self, services=None):
        super().__init__(agent_id="voiceover", services=services)
        self.contract_name = "voiceover"
        self.model_id = "eleven_turbo_v2_5"
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        # System fallback if DB and Brand identity both fail
        self.default_voice_id = "21m00Tcm4TlvDq8ikWAM" 

    def run(self, input_data, context, campaign_id=None):
        # context now includes the full venture row from our fixed DB query
        brand_snapshot = self.get_brand(context)
        
        if dry_run_enabled():
            result = self.dry_run(input_data, brand_snapshot)
        else:
            result = self.live_run(input_data, brand_snapshot, campaign_id)
        
        if isinstance(result, dict) and result.get("status") == "error":
            return result
            
        return self.validate_result(result, self.contract_name)

    def _resolve_voice_id(self, brand_snapshot):
        """
        Clean resolution hierarchy:
        1. Explicit venture setting (v.tts_voice_id)
        2. Brand identity preference (e.g. 'Male/Deep')
        3. System default (Rachel)
        """
        # 1. Check the new DB column we just added
        if brand_snapshot.get("tts_voice_id"):
            return brand_snapshot["tts_voice_id"]

        # 2. Fallback to descriptive identity logic
        identity = brand_snapshot.get("identity", {}).get("voice_preference", "").lower()
        if any(word in identity for word in ["male", "deep", "masculine"]):
            return "ErXw9S1p1pT6m4xT6m4x" # Thomas
            
        # 3. Ultimate safety fallback
        return self.default_voice_id

    def live_run(self, input_data, brand_snapshot, campaign_id=None):
        self.logger.info(f"🎙️ Voiceover Agent [LIVE]: Synthesizing audio via {self.model_id}...")

        if not isinstance(input_data, list) or not input_data:
            return {"status": "error", "message": f"VoiceoverAgent expected a non-empty list of segments, got: {type(input_data).__name__}"}

        voice_id = self._resolve_voice_id(brand_snapshot)

        full_text = " ".join([seg.get("text", "") for seg in input_data])
        directed_text = f"[calm, authoritative] {full_text}"

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
        headers = {
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        payload = {
            "text": directed_text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.8,
                "style": 0.2,
                "use_speaker_boost": True
            }
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                raise Exception(f"ElevenLabs API Error: {response.text}")

            response_json = response.json()
            audio_bytes = base64.b64decode(response_json["audio_base64"])

            venture_id = brand_snapshot.get("venture_id") or os.getenv("VENTURE_ID", "default-venture")

            base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
            output_dir = os.path.join(base_dir, "ventures", venture_id, "assets", "audio")
            os.makedirs(output_dir, exist_ok=True)

            timestamp = int(time.time())
            audio_path = os.path.join(output_dir, f"vo_{campaign_id}_{timestamp}.mp3")

            with open(audio_path, "wb") as f:
                f.write(audio_bytes)

            clean_path = audio_path.replace("\\", "/")
            self.logger.info(f"📁 [VO] Audio saved: {clean_path}")

            alignment = response_json.get("alignment", {})
            duration = alignment.get("character_end_times_seconds", [0])[-1]

            return self._build_output(
                audio_path=clean_path,
                duration=duration,
                alignment_data=alignment,
                voice_id=voice_id
            )

        except Exception as e:
            self.logger.error(f"💥 CRITICAL VO FAILURE: {e}")
            return {"status": "error", "message": str(e)}

    def dry_run(self, input_data, brand_snapshot):
        self.logger.info("🧪 Voiceover Agent [DRY RUN]: Generating mock response...")
        voice_id = self._resolve_voice_id(brand_snapshot)
        venture_id = brand_snapshot.get("venture_id", "default-venture")
        mock_path = f"ventures/{venture_id}/assets/audio/voiceover_mock.mp3"
        return self._build_output(mock_path, 15.0, {}, voice_id)

    def _build_output(self, audio_path, duration, alignment_data, voice_id):
        return {
            "status": "success",
            "vo_output": {
                "audio_file_path": audio_path,
                "alignment_data": alignment_data,
                "duration_seconds": max(round(duration, 3), 1.0),
                "provider_metadata": {
                    "provider": "elevenlabs",
                    "model_id": self.model_id,
                    "voice_id": voice_id
                }
            }
        }