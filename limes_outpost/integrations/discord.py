# limes_outpost/integrations/discord.py

import requests
import logging
from limes_outpost.config import settings

logger = logging.getLogger("limes_outpost.integrations.discord")

class OutpostSignalClient:
    def __init__(self, webhook_url=None):
        # Fallback to config if not provided directly
        self.url = webhook_url or getattr(settings, "discord_webhook_url", None)

    def send(self, embed: dict, content: str = None):
        if not self.url:
            logger.debug("Outpost Signal: No webhook URL configured, skipping notification.")
            return
        
        payload = {"embeds": [embed]}
        if content:
            payload["content"] = content
            
        try:
            # Short timeout; we don't want to hang the worker
            response = requests.post(self.url, json=payload, timeout=5)
            response.raise_for_status()
        except Exception as e:
            # The Golden Rule: Notifications must never break the build
            logger.warning(f"⚠️ Outpost Signal failed to broadcast: {e}")