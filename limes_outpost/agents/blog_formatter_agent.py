import os
import json
import time
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.utils.dry_run import dry_run_enabled


class BlogFormatterAgent(BaseAgent):
    """
    Blog Pipeline Step 3: The Formatter.

    Receives the raw blog_draft and produces the final deliverable:
    a clean, consistently structured markdown file saved to the venture's
    assets directory, mirroring how VoiceoverAgent saves audio files.

    Responsibilities:
      - Enforce subheading structure from brand profile
      - Inject YAML front matter (title, keyword, meta description, date)
      - Write the file to ventures/{venture_id}/assets/blog/
      - Return a standardised output dict for the Archivist to archive

    No LLM call needed — this is deterministic formatting, not generation.
    """

    def __init__(self, services=None):
        super().__init__(agent_id="blog_formatter", services=services)
        self.contract_name = "blog_formatter"

    def run(self, input_data, context, campaign_id=None):
        brand_snapshot = self.get_brand(context)

        if not input_data or not isinstance(input_data, dict):
            return {"status": "error", "message": "BlogFormatterAgent requires a blog_draft dict as input."}

        draft = input_data  # writer output is flat, no unwrap needed

        if dry_run_enabled():
            result = self.dry_run(draft, brand_snapshot, campaign_id)
        else:
            result = self.live_run(draft, brand_snapshot, campaign_id)

        if isinstance(result, dict) and result.get("status") == "error":
            return result

        return self.validate_result(result, self.contract_name)

    def live_run(self, draft, brand_snapshot, campaign_id):
        self.logger.info(f"📄 Blog Formatter Agent [LIVE]: Formatting '{draft.get('title', 'article')}'...")

        formatted_content = self._format_article(draft, brand_snapshot)
        file_path = self._save_to_disk(formatted_content, brand_snapshot, campaign_id)

        if not file_path:
            return {"status": "error", "message": "BlogFormatterAgent failed to write article to disk."}

        return self._build_final_output(draft, file_path, brand_snapshot)

    def dry_run(self, draft, brand_snapshot, campaign_id):
        self.logger.info(f"🧪 Blog Formatter Agent [DRY RUN]: Formatting mock article...")

        formatted_content = self._format_article(draft, brand_snapshot)
        venture_id = brand_snapshot.get("venture_id", "default-venture")
        mock_path = f"ventures/{venture_id}/assets/blog/article_mock_{campaign_id}.md"

        return self._build_final_output(draft, mock_path, brand_snapshot)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _format_article(self, draft, brand_snapshot):
        """Assembles the final markdown string with YAML front matter."""
        from datetime import datetime

        title = draft.get("title", "Untitled")
        meta_description = draft.get("meta_description", "")
        primary_keyword = draft.get("primary_keyword", "")
        body = draft.get("body_markdown", "")
        word_count = draft.get("word_count", 0)

        front_matter = f"""---
title: "{title}"
description: "{meta_description}"
keyword: "{primary_keyword}"
word_count: {word_count}
venture: "{brand_snapshot.get('venture_id', '')}"
date: "{datetime.utcnow().strftime('%Y-%m-%d')}"
---"""

        body_clean = body.strip()
        if not body_clean.startswith("# "):
            body_clean = f"# {title}\n\n{body_clean}"

        return f"{front_matter}\n\n{body_clean}\n"

    def _save_to_disk(self, content, brand_snapshot, campaign_id):
        """Saves the formatted article to the venture's blog assets directory."""
        venture_id = brand_snapshot.get("venture_id", "default-venture")

        from limes_outpost.config import settings
        output_dir = str(settings.ventures_dir / venture_id / "assets" / "blog")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = int(time.time())
        file_name = f"article_{campaign_id}_{timestamp}.md"
        file_path = os.path.join(output_dir, file_name)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            clean_path = file_path.replace("\\", "/")
            self.logger.info(f"📁 [Formatter] Article saved: {clean_path}")
            return clean_path

        except Exception as e:
            self.logger.error(f"❌ [Formatter] File write failed: {e}")
            return None

    def _build_final_output(self, draft, file_path, brand_snapshot):
        """Standardises output for the blog_formatter contract and Archivist."""
        return {
            "status": "success",
            "venture_id": brand_snapshot.get("venture_id", "unknown_venture"),
            "title": draft.get("title", "Untitled"),
            "file_path": file_path,
            "file_type": "markdown",
            "word_count": draft.get("word_count", 0),
            "primary_keyword": draft.get("primary_keyword", ""),
            "meta_description": draft.get("meta_description", ""),
            "primary_keyword_used": draft.get("primary_keyword_used", False),
            "cta_included": draft.get("cta_included", False),
        }