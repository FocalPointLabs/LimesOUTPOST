import json
import os
import time
import jwt
import requests
from .base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled

class VisualAgent(BaseAgent):
    def __init__(self, services=None):
        super().__init__(agent_id="visual", services=services)
        self.contract_name = "visual"
        self.ak = os.getenv("KLING_ACCESS_KEY")
        self.sk = os.getenv("KLING_SECRET_KEY")
        self.base_url = "https://api.klingai.com/v1"

    def _generate_token(self):
        """Generates the required Bearer JWT token for Kling API."""
        headers = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "iss": self.ak,
            "exp": int(time.time()) + 1800,
            "nbf": int(time.time()) - 5
        }
        token = jwt.encode(payload, self.sk, algorithm="HS256", headers=headers)
        return token

    def check_task_status(self, task_id):
        """
        Queries the Kling API for task status. 
        Required for the StorageAgent to know when to download.
        """
        token = self._generate_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}/videos/text2video/{task_id}"
        
        try:
            response = requests.get(url, headers=headers)
            res_json = response.json()
            if response.status_code == 200:
                data = res_json.get("data", {})
                status = data.get("task_status")
                
                if status == "succeed":
                    video_url = data.get("task_result", {}).get("videos", [{}])[0].get("url")
                    return {"status": "completed", "url": video_url}
                elif status == "failed":
                    return {"status": "failed", "error": data.get("task_status_msg")}
                else:
                    return {"status": "processing", "progress": data.get("task_progress", "0%")}
            return {"status": "error", "message": res_json.get("message")}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def run(self, input_data, context, campaign_id=None):
        """
        Accepts a scenes list directly (extracted by Orchestrator._map_inputs).
        Fetches brand context and validates the final output against the visual contract.
        """
        brand_snapshot = self.get_brand(context)

        if isinstance(input_data, list):
            script_input = {"scenes": input_data}
        elif isinstance(input_data, dict) and "scenes" in input_data:
            script_input = input_data
        else:
            return {"status": "error", "message": f"VisualAgent received unexpected input type: {type(input_data).__name__}. Expected a scenes list."}

        if not script_input["scenes"]:
            return {"status": "error", "message": "VisualAgent received an empty scenes list."}

        if dry_run_enabled():
            result = self.dry_run(script_input, brand_snapshot)
        else:
            result = self.live_run(script_input, brand_snapshot)

        if isinstance(result, dict) and result.get("status") == "error":
            return result

        return self.validate_result(result, self.contract_name)

    def live_run(self, script_input, brand_snapshot):
        """Generates detailed directorial prompts using Cerebras."""
        self.logger.info("🎬 Visual Agent [LIVE]: Drafting cinematic prompts...")

        system_prompt = f"""
        You are a Cinematic Director. Convert the following scenes into high-detail AI video prompts for Kling AI.
        STYLE: {brand_snapshot.get('visual_identity', {}).get('style_guide', 'Clean, modern, professional')}
        
        RETURN ONLY VALID JSON:
        {{
            "scenes": [
                {{ "scene_id": 1, "visual_prompt": "detailed cinematic description here", "camera_movement": "Pan right" }}
            ]
        }}
        """
        user_prompt = f"Script scenes: {json.dumps(script_input.get('scenes'))}"
        raw_response = self.llm.generate(system_prompt, user_prompt)

        try:
            clean_json = raw_response.strip().replace("```json", "").replace("```", "")
            visual_data = json.loads(clean_json)
            
            for i, scene in enumerate(visual_data.get("scenes", [])):
                if not scene.get("visual_prompt"):
                    original_desc = script_input.get("scenes")[i].get("visual_description")
                    scene["visual_prompt"] = original_desc

            return self._generate_kling_assets(visual_data, brand_snapshot)
        except Exception as e:
            self.logger.warning(f"⚠️ [VISUAL ERROR] Logic failed: {e}. Falling back to dry run.")
            return self.dry_run(script_input, brand_snapshot)

    def _generate_kling_assets(self, visual_data, brand_snapshot):
        """Dispatches ECONOMY text-to-video tasks to Kling with error handling."""
        scenes = visual_data.get("scenes", [])
        processed_assets = []
        token = self._generate_token()
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        for scene in scenes:
            prompt = scene.get("visual_prompt")
            if not prompt:
                continue

            payload = {
                "model": "kling-v1",
                "prompt": prompt,
                "negative_prompt": "deformed, blurry, low quality",
                "cfg_scale": 0.5,
                "mode": "std",
                "duration": "5",
                "aspect_ratio": "9:16"
            }

            try:
                response = requests.post(f"{self.base_url}/videos/text2video", json=payload, headers=headers)
                res_json = response.json()
                
                if response.status_code == 200:
                    task_id = res_json.get("data", {}).get("task_id")
                    processed_assets.append({
                        "scene_id": scene.get("scene_id"),
                        "visual_prompt": prompt,
                        "task_id": task_id,
                        "video_file_path": f"pending_{task_id}.mp4"
                    })
                else:
                    error_msg = res_json.get("message", "Unknown Kling Error")
                    self.logger.error(f"⚠️ Kling API Rejection: {error_msg}")
                    return {"status": "error", "message": f"Kling API: {error_msg}"}

            except Exception as e:
                return {"status": "error", "message": f"Visual Connection Error: {str(e)}"}

        return self._build_final_output({"scenes": processed_assets}, brand_snapshot)

    def _build_final_output(self, visual_data, brand_snapshot):
        return {
            "status": "success",
            "visual_output": {
                "scenes": visual_data.get("scenes", []),
                "video_metadata": {"provider": "Kling-JWT", "mode": "economy-std"}
            }
        }

    def dry_run(self, script_input, brand_snapshot):
        """Mocking visuals to allow the rest of the pipeline to run without credits."""
        self.logger.info("🧪 Visual Agent [DRY RUN]: Simulating Kling assets...")
        
        mock_scenes = []
        for i, scene in enumerate(script_input.get("scenes", [])):
            mock_scenes.append({
                "scene_id": scene.get("scene_id", i + 1),
                "visual_prompt": scene.get("visual_description", "Mock visual description"),
                "task_id": f"mock_task_{int(time.time())}_{i}",
                "video_file_path": f"pending_mock_{i}.mp4",
                "status": "simulated"
            })

        return {
            "status": "success",
            "visual_output": {
                "scenes": mock_scenes,
                "video_metadata": {
                    "provider": "Kling-MOCK",
                    "mode": "dry-run-safe"
                }
            }
        }