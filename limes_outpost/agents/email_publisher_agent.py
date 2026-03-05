import os
import base64
import json
import pickle
import time
from email.mime.text import MIMEText
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.agents.inbox_agent import GMAIL_SCOPES, TOKEN_CACHE_TEMPLATE, CLIENT_SECRETS_PATH
from limes_outpost.utils.dry_run import dry_run_enabled

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


class EmailPublisherAgent(BaseAgent):
    """
    Email Pipeline Step 4: The Sender.

    Sends approved email drafts via the Gmail API.
    Mirrors PublisherAgent's pattern exactly — called by a
    filtered PublishScheduler run (platform='email').

    Input (from publish_queue row, reconstructed by email scheduler):
      {
        "venture_id":   "yoga-zen-001",
        "to":           "recipient@example.com",
        "subject":      "Re: Your subject",
        "body":         "Full reply body text",
        "gmail_thread_id":  "thread_id_to_reply_in",
        "gmail_message_id": "message_id_to_reply_to",
      }

    Output:
      {
        "status":           "published",
        "platform_post_id": "gmail_message_id",
        "platform_url":     "gmail://thread/{thread_id}",
        "published_at":     "2026-02-27T...",
      }
    """

    def __init__(self, services=None):
        super().__init__(agent_id="email_publisher", services=services)

    def run(self, input_data, context, campaign_id=None):
        if dry_run_enabled():
            return self.dry_run(input_data, context)
        return self.live_run(input_data, context)

    # ------------------------------------------------------------------
    # Live run
    # ------------------------------------------------------------------

    def live_run(self, input_data, context):
        venture_id      = input_data.get("venture_id") or self.get_venture_id(context)
        to              = input_data.get("to")
        subject         = input_data.get("subject", "(no subject)")
        body            = input_data.get("body", "")
        thread_id       = input_data.get("gmail_thread_id")
        message_id      = input_data.get("gmail_message_id")

        if not to:
            return {"status": "error", "message": "No recipient address found in queue item."}

        self.logger.info(f"📤 Email Publisher [LIVE]: Sending reply to {to}...")

        try:
            service = self._get_authenticated_service(venture_id)
        except Exception as e:
            return {"status": "error", "message": f"Gmail auth failed: {e}"}

        try:
            message = self._build_message(
                to=to,
                subject=subject,
                body=body,
                thread_id=thread_id,
                reply_to_message_id=message_id,
            )

            sent = service.users().messages().send(
                userId="me",
                body=message
            ).execute()

            sent_id     = sent.get("id", "")
            thread_ref  = sent.get("threadId", thread_id or "")

            self.logger.info(f"✅ Email sent! Message ID: {sent_id}")

            return {
                "status":           "published",
                "platform_post_id": sent_id,
                "platform_url":     f"gmail://thread/{thread_ref}",
                "published_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

        except Exception as e:
            self.logger.error(f"❌ Gmail send failed: {e}")
            return {"status": "failed", "message": str(e)}

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    def dry_run(self, input_data, context):
        to      = input_data.get("to", "unknown@example.com")
        subject = input_data.get("subject", "Mock subject")
        self.logger.info(
            f"🧪 Email Publisher [DRY RUN]: Simulating send to {to} — '{subject}'"
        )
        mock_id = f"mock_email_{int(time.time())}"
        return {
            "status":           "published",
            "platform_post_id": mock_id,
            "platform_url":     f"gmail://thread/mock_thread_{mock_id}",
            "published_at":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_message(self, to, subject, body, thread_id=None, reply_to_message_id=None):
        """Constructs a Gmail API message dict, threading reply if IDs provided."""
        mime_msg = MIMEText(body, "plain")
        mime_msg["to"]      = to
        mime_msg["subject"] = subject

        # Threading headers so Gmail groups the reply correctly
        if reply_to_message_id:
            mime_msg["In-Reply-To"] = reply_to_message_id
            mime_msg["References"]  = reply_to_message_id

        raw     = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
        message = {"raw": raw}

        if thread_id:
            message["threadId"] = thread_id

        return message

    def _get_authenticated_service(self, venture_id):
        """Reuses the Gmail token cached by InboxAgent."""
        token_path = TOKEN_CACHE_TEMPLATE.format(venture_id=venture_id)
        creds = None

        if os.path.exists(token_path):
            with open(token_path, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                self.logger.info("🔄 Refreshing expired Gmail token...")
                creds.refresh(Request())
            else:
                self.logger.info("🔐 Opening browser for Gmail OAuth consent...")
                if not os.path.exists(CLIENT_SECRETS_PATH):
                    raise FileNotFoundError(
                        f"client_secrets.json not found at '{CLIENT_SECRETS_PATH}'."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRETS_PATH, scopes=GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)

            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, "wb") as f:
                pickle.dump(creds, f)

        return build("gmail", "v1", credentials=creds)