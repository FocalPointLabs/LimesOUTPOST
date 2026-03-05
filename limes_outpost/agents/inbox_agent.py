import os
import base64
import pickle
import json
import time
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Gmail readonly + send scopes — send is needed by EmailPublisherAgent later.
# Defining both here so the single token cache covers the full email workflow.
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",  # needed to mark as read
]

TOKEN_CACHE_TEMPLATE = "ventures/{venture_id}/gmail_token.pickle"
CLIENT_SECRETS_PATH  = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")

# How many unread threads to fetch per run
MAX_THREADS = int(os.getenv("INBOX_MAX_THREADS", "20"))


class InboxAgent(BaseAgent):
    """
    Email Pipeline Step 1: The Inbox Reader.

    Connects to Gmail, fetches unread threads, saves full thread
    history to email_threads table for downstream triage + drafting.

    Deduplication: gmail_thread_id has a UNIQUE constraint — already-fetched
    threads are silently skipped so re-runs are always safe.

    Auth: Same OAuth pattern as PublisherAgent, separate token cache
    per venture under ventures/{venture_id}/gmail_token.pickle.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="inbox", services=services)

    def run(self, input_data, context, campaign_id=None):
        if dry_run_enabled():
            return self.dry_run(input_data, context)
        return self.live_run(input_data, context)

    # ------------------------------------------------------------------
    # Live run
    # ------------------------------------------------------------------

    def live_run(self, input_data, context):
        venture_id = self.get_venture_id(context)
        self.logger.info(f"📬 Inbox Agent [LIVE]: Fetching unread threads for {venture_id}...")

        try:
            service = self._get_authenticated_service(venture_id)
        except Exception as e:
            return {"status": "error", "message": f"Gmail auth failed: {e}"}

        try:
            # Fetch unread thread IDs
            response = service.users().threads().list(
                userId="me",
                labelIds=["INBOX", "UNREAD"],
                maxResults=MAX_THREADS
            ).execute()

            threads = response.get("threads", [])
            if not threads:
                self.logger.info("📭 Inbox Agent: No unread threads found.")
                return {"status": "success", "fetched": 0, "message": "Inbox is empty."}

            self.logger.info(f"📬 Inbox Agent: Found {len(threads)} unread thread(s).")

            saved = 0
            skipped = 0

            for thread_stub in threads:
                thread_id = thread_stub["id"]

                # Fetch full thread with all messages
                full_thread = service.users().threads().get(
                    userId="me",
                    id=thread_id,
                    format="full"
                ).execute()

                saved_result = self._save_thread(full_thread, venture_id)
                if saved_result:
                    saved += 1
                else:
                    skipped += 1

            self.logger.info(
                f"✅ Inbox Agent: Saved {saved} new thread(s), "
                f"skipped {skipped} already-fetched."
            )
            return {
                "status":  "success",
                "fetched": saved,
                "skipped": skipped,
            }

        except Exception as e:
            self.logger.error(f"❌ Inbox Agent fetch failed: {e}")
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    def dry_run(self, input_data, context):
        venture_id = self.get_venture_id(context)
        self.logger.info(f"🧪 Inbox Agent [DRY RUN]: Simulating inbox fetch for {venture_id}...")

        ts = int(time.time())
        mock_threads = [
            {
                "gmail_thread_id":  f"mock_thread_001_{ts}",
                "gmail_message_id": f"mock_msg_001_{ts}",
                "sender_email":     "john@example.com",
                "sender_name":      "John Smith",
                "subject":          "Partnership opportunity for Yoga Zen",
                "body_snippet":     "Hi, I wanted to reach out about a potential collaboration...",
                "full_thread_json": {
                    "messages": [
                        {
                            "role": "sender",
                            "from": "john@example.com",
                            "body": "Hi, I wanted to reach out about a potential collaboration with Yoga Zen. We run a wellness newsletter with 50k subscribers and think there's a great fit here. Would love to chat.",
                            "date": "2026-02-27"
                        }
                    ]
                }
            },
            {
                "gmail_thread_id":  f"mock_thread_002_{ts}",
                "gmail_message_id": f"mock_msg_002_{ts}",
                "sender_email":     "unknown@spammer.com",
                "sender_name":      "Unknown Sender",
                "subject":          "URGENT: You've won a prize!!!",
                "body_snippet":     "Click here to claim your reward...",
                "full_thread_json": {
                    "messages": [
                        {
                            "role": "sender",
                            "from": "unknown@spammer.com",
                            "body": "Click here to claim your reward...",
                            "date": "2026-02-27"
                        }
                    ]
                }
            }
        ]

        saved = 0
        for mock in mock_threads:
            result = self._save_thread_direct(mock, venture_id)
            if result:
                saved += 1

        self.logger.info(f"🧪 Inbox Agent [DRY RUN]: Saved {saved} mock thread(s).")
        return {"status": "success", "fetched": saved, "skipped": 0}

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _save_thread(self, full_thread, venture_id):
        """Parses a raw Gmail API thread object and saves to DB.
        Returns True if saved, False if already exists (skipped).
        """
        try:
            messages     = full_thread.get("messages", [])
            thread_id    = full_thread.get("id")
            first_msg    = messages[0] if messages else {}
            latest_msg   = messages[-1] if messages else {}

            # Extract headers from latest message
            headers      = {
                h["name"].lower(): h["value"]
                for h in latest_msg.get("payload", {}).get("headers", [])
            }

            sender_raw   = headers.get("from", "")
            sender_name, sender_email = self._parse_sender(sender_raw)
            subject      = headers.get("subject", "(no subject)")
            message_id   = latest_msg.get("id", "")

            # Extract body snippet from latest message
            snippet      = latest_msg.get("snippet", "")

            # Build clean thread history for LLM context
            thread_history = self._build_thread_history(messages)

            parsed = {
                "gmail_thread_id":  thread_id,
                "gmail_message_id": message_id,
                "sender_email":     sender_email,
                "sender_name":      sender_name,
                "subject":          subject,
                "body_snippet":     snippet[:500],
                "full_thread_json": thread_history,
            }

            return self._save_thread_direct(parsed, venture_id)

        except Exception as e:
            self.logger.warning(f"⚠️ [Inbox] Failed to parse thread: {e}")
            return False

    def _save_thread_direct(self, parsed, venture_id):
        """Inserts a parsed thread dict into email_threads.
        Returns True if inserted, False if duplicate (ON CONFLICT DO NOTHING).
        """
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return False

        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.email_threads (
                        venture_id, gmail_thread_id, gmail_message_id,
                        sender_email, sender_name, subject,
                        body_snippet, full_thread_json, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'fetched')
                    ON CONFLICT (gmail_thread_id) DO NOTHING;
                """, (
                    venture_id,
                    parsed["gmail_thread_id"],
                    parsed["gmail_message_id"],
                    parsed["sender_email"],
                    parsed.get("sender_name", ""),
                    parsed.get("subject", ""),
                    parsed.get("body_snippet", ""),
                    json.dumps(parsed.get("full_thread_json", {})),
                ))
                inserted = cur.rowcount > 0
                conn.commit()
                return inserted
        except Exception as e:
            self.logger.warning(f"⚠️ [Inbox] DB save failed: {e}")
            return False
        finally:
            db_pool.putconn(conn)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_sender(self, raw):
        """Parses 'Name <email@domain.com>' into (name, email)."""
        import re
        match = re.match(r'^(.*?)\s*<(.+?)>$', raw.strip())
        if match:
            return match.group(1).strip().strip('"'), match.group(2).strip()
        # Raw string is just an email address
        return "", raw.strip()

    def _build_thread_history(self, messages):
        """Converts raw Gmail message list into clean thread history for LLM."""
        history = []
        for msg in messages:
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            body = self._extract_body(msg.get("payload", {}))
            history.append({
                "from":    headers.get("from", ""),
                "to":      headers.get("to", ""),
                "date":    headers.get("date", ""),
                "subject": headers.get("subject", ""),
                "body":    body[:3000],   # cap per message to keep LLM context sane
            })
        return {"messages": history}

    def _extract_body(self, payload):
        """Recursively extracts plain text body from Gmail message payload."""
        mime_type = payload.get("mimeType", "")

        if mime_type == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

        # Recurse into multipart
        for part in payload.get("parts", []):
            result = self._extract_body(part)
            if result:
                return result

        return ""

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_authenticated_service(self, venture_id):
        """Loads cached Gmail OAuth token or runs first-time consent flow."""
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
                    CLIENT_SECRETS_PATH,
                    scopes=GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)

            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, "wb") as f:
                pickle.dump(creds, f)
            self.logger.info(f"💾 Gmail token cached at {token_path}")

        return build("gmail", "v1", credentials=creds)