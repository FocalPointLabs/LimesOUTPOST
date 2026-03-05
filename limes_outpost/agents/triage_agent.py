import json
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled


class TriageAgent(BaseAgent):
    """
    Email Pipeline Step 2: The Triage Agent.

    Reads all 'fetched' email threads for a venture, runs each through
    the LLM to categorize, priority score, and determine whether a
    reply should be drafted. Also checks sender against the venture's
    whitelisted_emails for auto-draft eligibility.

    Output per thread:
      - category:       urgent / normal / low / ignore
      - priority_score: 1-10
      - is_whitelisted: bool
      - triage_notes:   LLM reasoning (useful for review + debugging)

    Threads categorized as 'ignore' are marked status='ignored' and
    skipped by DraftAgent. Everything else moves to status='triaged'.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="triage", services=services)

    def run(self, input_data, context, campaign_id=None):
        venture_id   = self.get_venture_id(context)
        whitelisted  = self._load_whitelist(venture_id)
        threads      = self._fetch_fetched_threads(venture_id)

        if not threads:
            self.logger.info("📭 Triage Agent: No new threads to triage.")
            return {"status": "success", "triaged": 0}

        self.logger.info(f"🔍 Triage Agent: Processing {len(threads)} thread(s)...")

        triaged  = 0
        ignored  = 0

        for thread in threads:
            result = self._triage_thread(thread, context, whitelisted)

            is_whitelisted = thread["sender_email"].lower() in whitelisted
            final_status   = "ignored" if result["category"] == "ignore" else "triaged"

            self._save_triage(
                thread_id      = thread["id"],
                category       = result["category"],
                priority_score = result["priority_score"],
                is_whitelisted = is_whitelisted,
                triage_notes   = result["triage_notes"],
                status         = final_status,
            )

            if final_status == "ignored":
                ignored += 1
                self.logger.info(
                    f"🗑️  Ignored: '{thread['subject'][:60]}' "
                    f"(category: {result['category']})"
                )
            else:
                triaged += 1
                self.logger.info(
                    f"✅ Triaged: '{thread['subject'][:60]}' → "
                    f"{result['category'].upper()} | "
                    f"priority {result['priority_score']}/10 | "
                    f"whitelisted: {is_whitelisted}"
                )

        return {
            "status":  "success",
            "triaged": triaged,
            "ignored": ignored,
        }

    # ------------------------------------------------------------------
    # Triage logic
    # ------------------------------------------------------------------

    def _triage_thread(self, thread, context, whitelisted):
        """Runs a single thread through the LLM for categorization."""
        brand       = self.get_brand(context)
        owner_name  = brand.get("name", "the owner")
        niche       = brand.get("niche", "Wellness")

        is_whitelisted = thread["sender_email"].lower() in whitelisted

        thread_text = self._format_thread_for_llm(thread)

        system_prompt = f"""
You are an expert email triage assistant for {owner_name}, a {niche} content creator.

Your job is to analyze an email thread and return a structured triage decision.

CATEGORIES:
- urgent:  Requires immediate attention (time-sensitive opportunities, critical issues, direct business asks from known contacts)
- normal:  Standard business communication worth a thoughtful reply
- low:     FYI emails, newsletters, non-actionable updates
- ignore:  Spam, cold outreach from unknown senders, automated notifications

SENDER CONTEXT:
- Is whitelisted (known contact): {is_whitelisted}
- Whitelisted senders should generally be categorized urgent or normal unless clearly irrelevant.
- Unknown senders should be carefully evaluated — most cold outreach is 'ignore' unless clearly high value.

RESPONSE FORMAT — return valid JSON only, no preamble:
{{
    "category": "urgent|normal|low|ignore",
    "priority_score": <integer 1-10, 10 being most urgent>,
    "triage_notes": "2-3 sentence explanation of your decision and what the email is about"
}}
"""

        user_prompt = f"Triage this email thread:\n\n{thread_text}"

        if dry_run_enabled():
            return self._mock_triage(thread, is_whitelisted)

        raw = self.llm.generate(system_prompt, user_prompt)

        try:
            result = json.loads(raw) if isinstance(raw, str) else raw
            # Validate expected keys exist
            assert "category" in result and "priority_score" in result
            return result
        except Exception as e:
            self.logger.warning(f"⚠️ [Triage] LLM parse failed: {e}. Using fallback.")
            return self._mock_triage(thread, is_whitelisted)

    def _mock_triage(self, thread, is_whitelisted):
        """Deterministic dry-run triage based on simple heuristics."""
        subject = thread.get("subject", "").lower()
        sender  = thread.get("sender_email", "").lower()

        spam_signals = ["prize", "winner", "click here", "urgent", "!!!"]
        is_spam      = any(s in subject for s in spam_signals) or "spammer" in sender

        if is_spam:
            return {
                "category":      "ignore",
                "priority_score": 1,
                "triage_notes":  "Detected spam signals in subject line. No action needed."
            }
        elif is_whitelisted:
            return {
                "category":      "urgent",
                "priority_score": 8,
                "triage_notes":  "Whitelisted sender with a business inquiry. Deserves a prompt, thoughtful reply."
            }
        else:
            return {
                "category":      "normal",
                "priority_score": 5,
                "triage_notes":  "Unknown sender with what appears to be a legitimate inquiry. Worth reviewing."
            }

    def _format_thread_for_llm(self, thread):
        """Formats thread data into readable text for the LLM prompt."""
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
                lines.append(f"")
                lines.append(msg.get("body", "(no body)"))
                lines.append("")
        else:
            lines.append(thread.get("body_snippet", "(no content)"))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _fetch_fetched_threads(self, venture_id):
        """Returns all threads with status='fetched' for this venture."""
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return []
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        id, venture_id, gmail_thread_id,
                        sender_email, sender_name, subject,
                        body_snippet, full_thread_json
                    FROM public.email_threads
                    WHERE venture_id = %s AND status = 'fetched'
                    ORDER BY created_at ASC;
                """, (venture_id,))
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            db_pool.putconn(conn)

    def _load_whitelist(self, venture_id):
        """Loads whitelisted_emails from ventures table as a lowercase set."""
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return set()
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT whitelisted_emails FROM public.ventures WHERE id = %s",
                    (venture_id,)
                )
                row = cur.fetchone()
                if row and row[0]:
                    return {email.lower() for email in row[0]}
                return set()
        finally:
            db_pool.putconn(conn)

    def _save_triage(
        self, thread_id, category, priority_score,
        is_whitelisted, triage_notes, status
    ):
        """Updates email_threads row with triage results."""
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE public.email_threads SET
                        category       = %s,
                        priority_score = %s,
                        is_whitelisted = %s,
                        triage_notes   = %s,
                        status         = %s,
                        updated_at     = NOW()
                    WHERE id = %s;
                """, (
                    category, priority_score, is_whitelisted,
                    triage_notes, status, str(thread_id)
                ))
                conn.commit()
        finally:
            db_pool.putconn(conn)