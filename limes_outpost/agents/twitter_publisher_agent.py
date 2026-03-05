import os
import time
import pickle
import requests
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled

from requests_oauthlib import OAuth2Session
from google_auth_oauthlib.flow import InstalledAppFlow

# X API v2 endpoints
X_TWEET_URL       = "https://api.twitter.com/2/tweets"
X_MENTIONS_URL    = "https://api.twitter.com/2/users/{user_id}/mentions"
X_AUTH_URL        = "https://twitter.com/i/oauth2/authorize"
X_TOKEN_URL       = "https://api.twitter.com/2/oauth2/token"

X_SCOPES          = ["tweet.read", "tweet.write", "users.read", "offline.access"]
TOKEN_CACHE_TEMPLATE = "ventures/{venture_id}/x_token.pickle"


class TwitterPublisherAgent(BaseAgent):
    """
    Social Publisher: X (Twitter).

    Posts approved tweets via X API v2 using OAuth 2.0 PKCE.

    Input (from publish_queue row):
      {
        "venture_id": "yoga-zen-001",
        "tweet_text": "Ready-to-post tweet text",
        "reply_to_tweet_id": "optional — for social replies"
      }

    Output:
      {
        "status":           "published",
        "platform_post_id": "tweet_id",
        "platform_url":     "https://x.com/i/web/status/{tweet_id}",
        "published_at":     "2026-02-27T...",
      }

    Auth note:
      X OAuth 2.0 PKCE requires a client ID and client secret from your
      X Developer Portal app. Set these in .env:
        X_CLIENT_ID=your_client_id
        X_CLIENT_SECRET=your_client_secret
        X_REDIRECT_URI=http://localhost:8080/callback
    """

    def __init__(self, services=None):
        super().__init__(agent_id="twitter_publisher", services=services)
        self.client_id     = os.getenv("X_CLIENT_ID")
        self.client_secret = os.getenv("X_CLIENT_SECRET")
        self.redirect_uri  = os.getenv("X_REDIRECT_URI", "http://localhost:8080/callback")

    def run(self, input_data, context, campaign_id=None):
        if dry_run_enabled():
            return self.dry_run(input_data, context)
        return self.live_run(input_data, context)

    # ------------------------------------------------------------------
    # Live run
    # ------------------------------------------------------------------

    def live_run(self, input_data, context):
        venture_id      = input_data.get("venture_id") or self.get_venture_id(context)
        tweet_text      = input_data.get("tweet_text") or input_data.get("description")
        reply_to_id     = input_data.get("reply_to_tweet_id")

        if not tweet_text:
            return {"status": "error", "message": "No tweet_text found in queue item."}

        if len(tweet_text) > 280:
            return {"status": "error", "message": f"Tweet exceeds 280 chars ({len(tweet_text)})."}

        self.logger.info(f"📤 Twitter Publisher [LIVE]: Posting tweet for {venture_id}...")

        try:
            token = self._get_token(venture_id)
        except Exception as e:
            return {"status": "error", "message": f"X auth failed: {e}"}

        headers = {
            "Authorization": f"Bearer {token['access_token']}",
            "Content-Type":  "application/json",
        }

        payload = {"text": tweet_text}
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}

        try:
            response = requests.post(X_TWEET_URL, json=payload, headers=headers)
            response.raise_for_status()
            data     = response.json().get("data", {})
            tweet_id = data.get("id", "")

            self.logger.info(f"✅ Tweet posted! ID: {tweet_id}")

            return {
                "status":           "published",
                "platform_post_id": tweet_id,
                "platform_url":     f"https://x.com/i/web/status/{tweet_id}",
                "published_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

        except Exception as e:
            self.logger.error(f"❌ Twitter post failed: {e}")
            return {"status": "failed", "message": str(e)}

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    def dry_run(self, input_data, context):
        tweet_text = input_data.get("tweet_text") or input_data.get("description", "Mock tweet")
        self.logger.info(f"🧪 Twitter Publisher [DRY RUN]: Simulating post...")
        self.logger.info(f"   Tweet ({len(tweet_text)} chars): {tweet_text[:80]}...")
        mock_id = f"mock_tweet_{int(time.time())}"
        return {
            "status":           "published",
            "platform_post_id": mock_id,
            "platform_url":     f"https://x.com/i/web/status/{mock_id}",
            "published_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # ------------------------------------------------------------------
    # Auth — OAuth 2.0 PKCE
    # ------------------------------------------------------------------

    def _get_token(self, venture_id):
        """Loads cached X OAuth token or runs first-time PKCE consent flow."""
        token_path = TOKEN_CACHE_TEMPLATE.format(venture_id=venture_id)

        # Load cached token
        if os.path.exists(token_path):
            with open(token_path, "rb") as f:
                token = pickle.load(f)

            # Refresh if expired
            if self._token_needs_refresh(token):
                token = self._refresh_token(token)
                self._cache_token(token, token_path)

            return token

        # First-time consent flow
        return self._run_consent_flow(venture_id, token_path)

    def _run_consent_flow(self, venture_id, token_path):
        """Opens browser for X OAuth 2.0 PKCE consent."""
        if not self.client_id:
            raise ValueError(
                "X_CLIENT_ID not set in .env. "
                "Create an app at developer.twitter.com and add X_CLIENT_ID, "
                "X_CLIENT_SECRET, and X_REDIRECT_URI to your .env file."
            )

        self.logger.info("🔐 Opening browser for X OAuth consent...")

        oauth = OAuth2Session(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            scope=X_SCOPES
        )

        auth_url, state = oauth.authorization_url(
            X_AUTH_URL,
            code_challenge_method="S256"
        )

        print(f"\n🔗 Open this URL in your browser to authorize X:\n{auth_url}\n")
        redirect_response = input("Paste the full redirect URL after authorizing: ").strip()

        token = oauth.fetch_token(
            X_TOKEN_URL,
            authorization_response=redirect_response,
            client_secret=self.client_secret,
            code_verifier=oauth._code_verifier,
        )

        self._cache_token(token, token_path)
        self.logger.info(f"💾 X token cached at {token_path}")
        return token

    def _refresh_token(self, token):
        """Refreshes an expired X OAuth token."""
        self.logger.info("🔄 Refreshing expired X token...")
        oauth    = OAuth2Session(client_id=self.client_id, token=token)
        new_token = oauth.refresh_token(
            X_TOKEN_URL,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        return new_token

    def _token_needs_refresh(self, token):
        expires_at = token.get("expires_at", 0)
        return time.time() > expires_at - 60

    def _cache_token(self, token, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(token, f)