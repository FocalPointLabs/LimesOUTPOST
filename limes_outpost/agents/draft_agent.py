import json
import os
from pathlib import Path
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled


class DraftAgent(BaseAgent):
    """
    Email Pipeline Step 3: The Draft Agent.

    Reads all 'triaged' threads (excluding ignored) and generates
    a reply draft for each one. Drafts are grounded in the owner's
    communication style from ventures/{venture_id}/personal_profile.json.

    Whitelisted senders get a more personalized, warmer reply.
    Non-whitelisted but triaged threads get a professional but
    measured response.

    Each draft is inserted into publish_queue with platform='email'
    and status='pending_review' for operator approval before sending.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="draft", services=services)
        self.contract_name = "email_draft"
        # personal_profile is loaded per-run from venture dir in run()
        self.personal_profile = {}

    def run(self, input_data, context, campaign_id=None):
        venture_id = self.get_venture_id(context)

        # Load per-venture personal profile
        self.personal_profile = self._load_personal_profile(venture_id)

        threads = self._fetch_triaged_threads(venture_id)

        if not threads:
            self.logger.info("📭 Draft Agent: No triaged threads to draft.")
            return {"status": "success", "drafted": 0}

        self.logger.info(f"✍️  Draft Agent: Drafting replies for {len(threads)} thread(s)...")

        drafted = 0
        for thread in threads:
            draft_body = self._generate_draft(thread, context)
            if not draft_body:
                continue

            enqueued = self._enqueue_draft(thread, draft_body, venture_id)
            if enqueued:
                self._mark_drafted(thread["id"])
                drafted += 1
                self.logger.info(
                    f"📝 Drafted reply for: '{thread['subject'][:60]}' "
                    f"→ {thread['sender_email']}"
                )

        return {"status": "success", "drafted": drafted}

    # ------------------------------------------------------------------
    # Draft generation
    # ------------------------------------------------------------------

    def _generate_draft(self, thread, context):
        """Generates a reply draft using the LLM."""
        brand      = self.get_brand(context)
        owner_name = self.personal_profile.get("owner", brand.get("name", "the owner"))
        comm_style = self.personal_profile.get("communication_style", "direct, professional")
        sign_off   = self.personal_profile.get("sign_off", owner_name)
        brand_name = brand.get("name", "")
        niche      = brand.get("niche", "Wellness")

        thread_text    = self._format_thread_for_llm(thread)
        is_whitelisted = thread.get("is_whitelisted", False)
        category       = thread.get("category", "normal")
        triage_notes   = thread.get("triage_notes", "")

        warmth = (
            "This is a known contact — be warm, direct, and personal."
            if is_whitelisted
            else "This sender is not a known contact — be professional but measured."
        )

        urgency = (
            "This is marked URGENT — keep the reply concise and action-oriented."
            if category == "urgent"
            else "This is a normal priority email — a thoughtful, complete reply is appropriate."
        )

        system_prompt = f"""
You are drafting an email reply on behalf of {owner_name}, the founder of {brand_name} ({niche}).

OWNER'S COMMUNICATION STYLE: {comm_style}

REPLY GUIDELINES:
- {warmth}
- {urgency}
- Match the tone and length of the original email — don't over-explain
- Sign off as: {sign_off}
- Do NOT use filler phrases like "I hope this email finds you well"
- Do NOT use corporate jargon
- Be human, be real

CONTEXT FROM TRIAGE:
{triage_notes}

RESPONSE FORMAT — return valid JSON only, no preamble:
{{
    "subject": "Re: <original subject or updated if needed>",
    "body": "The full email reply body, plain text, no markdown"
}}
"""

        user_prompt = f"Draft a reply to this email thread:\n\n{thread_text}"

        if dry_run_enabled():
            return self.validate_result(
                self._mock_draft(thread, owner_name, sign_off),
                self.contract_name
            )

        raw = self.llm.generate(system_prompt, user_prompt)

        try:
            result = json.loads(raw) if isinstance(raw, str) else raw
            return self.validate_result(result, self.contract_name)
        except Exception as e:
            self.logger.warning(f"⚠️ [Draft] Contract breach or parse failure: {e}. Using fallback.")
            return self._mock_draft(thread, owner_name, sign_off)

    def _mock_draft(self, thread, owner_name, sign_off=None):
        """Dry-run fallback draft."""
        subject     = thread.get("subject", "Your message")
        sender_name = thread.get("sender_name") or thread.get("sender_email", "there")
        first_name  = sender_name.split()[0] if sender_name else "there"
        sign_off    = sign_off or owner_name

        return {
            "subject": f"Re: {subject}",
            "body": (
                f"Hey {first_name},\n\n"
                f"Thanks for reaching out — really appreciate it.\n\n"
                f"[DRAFT PLACEHOLDER — this reply was generated in dry run mode. "
                f"Replace with actual content before sending.]\n\n"
                f"Best,\n{sign_off}"
            )
        }

    def _format_thread_for_llm(self, thread):
        """Formats thread for LLM prompt."""
        lines = [
            f"FROM:    {thread.get('sender_name', '')} <{thread.get('sender_email', '')}>",
            f"SUBJECT: {thread.get('subject', '(no subject)')}",
            f"",
        ]

        thread_data = thread.get("full_thread_json") or {}
        messages    = thread_data.get("messages", [])

        if messages:
            for i, msg in enumerate(messages, 1):
                lines.append(f"--- Message {i} ---")
                lines.append(f"From: {msg.get('from', '')}")
                lines.append(f"Date: {msg.get('date', '')}")
                lines.append("")
                lines.append(msg.get("body", "(no body)"))
                lines.append("")
        else:
            lines.append(thread.get("body_snippet", "(no content)"))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Queue insertion
    # ------------------------------------------------------------------

    def _enqueue_draft(self, thread, draft, venture_id):
        """Inserts the draft into publish_queue with platform='email'."""
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return False

        email_meta = json.dumps({
            "to":               thread["sender_email"],
            "sender_name":      thread.get("sender_name", ""),
            "gmail_thread_id":  thread.get("gmail_thread_id", ""),
            "gmail_message_id": thread.get("gmail_message_id", ""),
            "category":         thread.get("category", "normal"),
            "priority_score":   thread.get("priority_score", 5),
            "is_whitelisted":   thread.get("is_whitelisted", False),
        })

        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                # Sentinel asset row — email drafts have no real file
                placeholder_path = (
                    f"email_draft/{venture_id}/"
                    f"{thread.get('gmail_thread_id', 'unknown_thread')}"
                )
                cur.execute("""
                    INSERT INTO public.assets (file_path, file_type, metadata, venture_id)
                    VALUES (%s, 'email_draft', %s, %s)
                    RETURNING id;
                """, (
                    placeholder_path,
                    json.dumps({"venture_id": venture_id, "platform": "email"}),
                    venture_id,
                ))
                asset_id = cur.fetchone()[0]

                cur.execute("""
                    INSERT INTO public.publish_queue
                        (asset_id, venture_id, platform, status, title, description, tags)
                    VALUES (%s, %s, 'email', 'pending_review', %s, %s, %s);
                """, (
                    str(asset_id),
                    venture_id,
                    draft["subject"][:200],
                    draft["body"],
                    [email_meta],
                ))
                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            self.logger.warning(f"⚠️ [Draft] Failed to enqueue draft: {e}")
            return False
        finally:
            db_pool.putconn(conn)

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _fetch_triaged_threads(self, venture_id):
        """Returns all threads with status='triaged' (excludes ignored)."""
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return []
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        id, venture_id, gmail_thread_id, gmail_message_id,
                        sender_email, sender_name, subject,
                        body_snippet, full_thread_json,
                        category, priority_score, is_whitelisted, triage_notes
                    FROM public.email_threads
                    WHERE venture_id = %s AND status = 'triaged'
                    ORDER BY priority_score DESC, created_at ASC;
                """, (venture_id,))
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            db_pool.putconn(conn)

    def _mark_drafted(self, thread_id):
        """Updates thread status to 'drafted'."""
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE public.email_threads
                    SET status = 'drafted', updated_at = NOW()
                    WHERE id = %s;
                """, (str(thread_id),))
                conn.commit()
        finally:
            db_pool.putconn(conn)

    def _load_personal_profile(self, venture_id: str) -> dict:
        """
        Loads per-venture personal_profile.json from:
          ventures/{venture_id}/personal_profile.json

        Falls back to sensible defaults if not found.
        """
        profile_path = Path("ventures") / venture_id / "personal_profile.json"
        try:
            if profile_path.exists():
                with open(profile_path, "r", encoding="utf-8") as f:
                    profile = json.load(f)
                    self.logger.info(f"[Draft] Loaded personal profile for {venture_id}")
                    return profile
            else:
                self.logger.warning(
                    f"⚠️ [Draft] No personal_profile.json found for '{venture_id}' "
                    f"at {profile_path}. Using defaults. "
                    f"Create ventures/{venture_id}/personal_profile.json to customise."
                )
        except Exception as e:
            self.logger.warning(f"⚠️ [Draft] Could not load personal_profile.json: {e}")
        return {}