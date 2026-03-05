import os
import time
import requests
from limes_outpost.utils.logger import LimesOutpostLogger

class StorageAgent:
    def __init__(self, visual_agent):
        self.visual_agent = visual_agent
        self.storage_path = "./outputs/videos"
        self.logger = LimesOutpostLogger()
        os.makedirs(self.storage_path, exist_ok=True)

    def poll_and_download(self, visual_output, timeout=600, interval=30):
        """
        Polls Kling for multiple scenes (Visual Phase).
        Matches the method name expected by orchestrator.py
        """
        scenes = visual_output.get("scenes", [])
        updated_scenes = []

        for scene in scenes:
            task_id = scene.get("task_id")
            scene_id = scene.get("scene_id")

            # SAFETY: Skip polling if we are in Dry Run / Mock mode
            if not task_id or "mock" in str(task_id):
                self.logger.info(f"🧪 Storage Agent: Using Mock Asset for Scene {scene_id}")
                updated_scenes.append(scene)
                continue

            self.logger.info(f"📦 Storage Agent: Monitoring Scene {scene_id} (Task: {task_id})...")
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                status_check = self.visual_agent.check_task_status(task_id)
                
                if status_check["status"] == "completed":
                    video_url = status_check["url"]
                    local_path = self._download_file(video_url, f"scene_{scene_id}_{task_id}")
                    scene["video_file_path"] = local_path
                    self.logger.info(f"✅ Scene {scene_id} Downloaded: {local_path}")
                    break
                elif status_check["status"] == "failed":
                    self.logger.error(f"❌ Scene {scene_id} Failed: {status_check.get('message')}")
                    break
                
                time.sleep(interval)
            
            updated_scenes.append(scene)

        return updated_scenes

    def poll_and_download_render(self, composer_output, timeout=600, interval=20):
        """Polls Creatomate until the render succeeds, then downloads the final video."""
        render_id = composer_output.get("render_id")
        
        # Safety: skip polling for mock/dry run renders
        if not render_id or "mock" in str(render_id):
            self.logger.info(f"🧪 Storage Agent: Mock render detected, skipping Creatomate poll.")
            return composer_output.get("local_video_path")

        api_key = os.getenv("CREATOMATE_API_KEY")
        if not api_key:
            self.logger.error(f"❌ Storage Agent: CREATOMATE_API_KEY not set, cannot poll render.")
            return None

        poll_url = f"https://api.creatomate.com/v1/renders/{render_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        self.logger.info(f"⏳ Storage Agent: Polling Creatomate render {render_id}...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(poll_url, headers=headers)
                response.raise_for_status()
                render_data = response.json()
                
                status = render_data.get("status")
                self.logger.info(f"   Creatomate status: {status}")

                if status == "succeeded":
                    video_url = render_data.get("url")
                    if not video_url:
                        self.logger.error(f"❌ Storage Agent: Render succeeded but no URL returned.")
                        return None
                    self.logger.info(f"✅ Render complete. Downloading from {video_url}...")
                    return self._download_render(video_url, render_id)
                
                elif status == "failed":
                    error = render_data.get("error_message", "Unknown Creatomate error")
                    self.logger.error(f"❌ Storage Agent: Render failed — {error}")
                    return None
                
                # status is 'planned' or 'rendering' — keep waiting
                time.sleep(interval)
            except Exception as e:
                self.logger.error(f"❌ Storage Agent: Creatomate poll error — {e}")
                return None

        self.logger.error(f"❌ Storage Agent: Render timed out after {timeout}s for render_id {render_id}")
        return None

    def _download_render(self, url, render_id):
        """Downloads the final composed video from Creatomate's CDN."""
        file_name = f"render_{render_id}.mp4"
        full_path = os.path.join(self.storage_path, file_name)
        
        # Normalize slashes for cross-platform DB consistency
        clean_path = full_path.replace("\\", "/")
        
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            with open(full_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            self.logger.info(f"📁 Storage Agent: Render saved to {clean_path}")
            return clean_path
        except Exception as e:
            self.logger.error(f"❌ Storage Agent: Download failed — {e}")
            return None

    def _download_file(self, url, file_id):
        """Internal helper for scene-based downloads."""
        file_name = f"{file_id}.mp4"
        full_path = os.path.join(self.storage_path, file_name)
        
        try:
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                with open(full_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return full_path
        except Exception as e:
            self.logger.error(f"❌ Download Error: {e}")
        return None