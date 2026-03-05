import os
import json
import time
import pickle
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled

# Google API client libs — added to requirements.txt separately
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# Scopes required for video upload
YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]

# Token cache path — stored per venture so multi-venture auth is isolated
TOKEN_CACHE_TEMPLATE = "ventures/{venture_id}/youtube_token.pickle"
CLIENT_SECRETS_PATH = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")


class PublisherAgent(BaseAgent):
    """
    Distribution Layer: YouTube Shorts Publisher.

    Uploads a completed video asset to YouTube Shorts via the
    YouTube Data API v3. Shorts designation is automatic for
    vertical 9:16 videos under 60 seconds — no special API needed.

    Auth flow:
      - First run: opens browser for OAuth consent, caches token to disk.
      - Subsequent runs: loads cached token, refreshes silently if expired.
      - Token stored per-venture so multi-venture setups stay isolated.

    Input (from publish_queue row):
      {
        "asset_id":    "uuid",
        "file_path":   "path/to/video.mp4",
        "title":       "Video title",
        "description": "Video description",
        "tags":        ["yoga", "shorts"],
        "venture_id":  "yoga-zen-001"
      }

    Output:
      {
        "status":           "published",
        "platform_post_id": "youtube_video_id",
        "platform_url":     "https://youtu.be/...",
        "published_at":     "2026-02-27T...",
      }
    """

    def __init__(self, services=None):
        super().__init__(agent_id="publisher", services=services)

    def run(self, input_data, context, campaign_id=None):
        if dry_run_enabled():
            return self.dry_run(input_data, context)
        return self.live_run(input_data, context)

    # ------------------------------------------------------------------
    # Live run
    # ------------------------------------------------------------------

    def live_run(self, input_data, context):
        venture_id = input_data.get("venture_id") or self.get_venture_id(context)
        file_path   = input_data.get("file_path")
        title       = input_data.get("title", "New Video")
        description = input_data.get("description", "")
        tags        = input_data.get("tags", [])

        if not file_path or not os.path.exists(file_path):
            return {"status": "error", "message": f"Video file not found: {file_path}"}

        self.logger.info(f"📤 Publisher [LIVE]: Uploading '{title}' to YouTube Shorts...")

        try:
            youtube = self._get_authenticated_service(venture_id)
        except Exception as e:
            return {"status": "error", "message": f"YouTube auth failed: {e}"}

        body = {
            "snippet": {
                "title":       title[:100],   # YouTube 100-char limit
                "description": description[:5000],
                "tags":        tags,
                "categoryId":  "26",   # 26 = Howto & Style (fits wellness)
            },
            "status": {
                "privacyStatus":           "public",
                "selfDeclaredMadeForKids": False,
            }
        }

        media = MediaFileUpload(
            file_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 5   # 5MB chunks
        )

        try:
            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    self.logger.info(f"⬆️  Upload progress: {progress}%")

            video_id  = response.get("id")
            video_url = f"https://youtu.be/{video_id}"

            self.logger.info(f"✅ Published! YouTube ID: {video_id} → {video_url}")

            return {
                "status":           "published",
                "platform_post_id": video_id,
                "platform_url":     video_url,
                "published_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

        except Exception as e:
            self.logger.error(f"❌ YouTube upload failed: {e}")
            return {"status": "failed", "message": str(e)}

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    def dry_run(self, input_data, context):
        title = input_data.get("title", "Mock Video")
        self.logger.info(f"🧪 Publisher [DRY RUN]: Simulating upload for '{title}'...")
        mock_id = f"mock_yt_{int(time.time())}"
        return {
            "status":           "published",
            "platform_post_id": mock_id,
            "platform_url":     f"https://youtu.be/{mock_id}",
            "published_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _get_authenticated_service(self, venture_id):
        """Loads cached OAuth token or runs first-time browser consent flow."""
        token_path = TOKEN_CACHE_TEMPLATE.format(venture_id=venture_id)
        creds = None

        # Load cached token if it exists
        if os.path.exists(token_path):
            with open(token_path, "rb") as f:
                creds = pickle.load(f)

        # Refresh if expired, or run full consent flow if no creds
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                self.logger.info("🔄 Refreshing expired YouTube token...")
                creds.refresh(Request())
            else:
                self.logger.info("🔐 Opening browser for YouTube OAuth consent...")
                if not os.path.exists(CLIENT_SECRETS_PATH):
                    raise FileNotFoundError(
                        f"client_secrets.json not found at '{CLIENT_SECRETS_PATH}'. "
                        f"Download it from Google Cloud Console → APIs & Services → Credentials."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRETS_PATH,
                    scopes=YOUTUBE_UPLOAD_SCOPE
                )
                creds = flow.run_local_server(port=0)

            # Cache the token for next time
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, "wb") as f:
                pickle.dump(creds, f)
            self.logger.info(f"💾 YouTube token cached at {token_path}")

        return build("youtube", "v3", credentials=creds)