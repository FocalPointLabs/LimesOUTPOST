from datetime import datetime

class LimesOutpostAdapter:
    def __init__(self, client):
        self.client = client

    def _get_reliability_stats(self, stats):
        """Calculates reliability percentage and determines status color."""
        total = stats.get('total_tracked_items', 0)
        success = stats.get('recent_renders', 0)
        
        # Calculate Reliability
        reliability = (success / total * 100) if total > 0 else 100.0
        
        # Determine Color (LimesOutpost Green > 90, Amber > 75, Violation Red below)
        if reliability >= 90:
            color = 0x00C896 
            status_emoji = "🟢 NOMINAL"
        elif reliability >= 75:
            color = 0xF5A623
            status_emoji = "🟡 FRICTION"
        else:
            color = 0xFF4444
            status_emoji = "🔴 CRITICAL"
            
        return reliability, color, status_emoji

    def broadcast_pulse(self, venture_id, stats, briefing_text):
        reliability, color, status_label = self._get_reliability_stats(stats)
        
        # Clean the briefing text to show only the AI's insight
        clean_brief = briefing_text.split('🤖 ASSISTANT BRIEF:')[1].strip() if '🤖 ASSISTANT BRIEF:' in briefing_text else briefing_text

        embed = {
            "title": f"📡 STATE OF THE OUTPOST — {venture_id}",
            "color": color,
            "description": f"**System Reliability:** `{reliability:.1f}%` ({status_label})",
            "fields": [
                {
                    "name": "📊 TELEMETRY",
                    "value": (
                        f"**Yield:** `{stats['recent_renders']}` units\n"
                        f"**Blockers:** `{stats['failed_contracts']}` breaches\n"
                        f"**Load:** `{stats['total_tracked_items']}` tracked"
                    ),
                    "inline": False
                },
                {
                    "name": "🤖 ASSISTANT BRIEFING", 
                    "value": f"```yaml\n{clean_brief}\n```"
                }
            ],
            "footer": {"text": f"LimesOutpost Outpost // Reliability Protocol // {datetime.now().strftime('%H:%M:%S')}"}
        }
        self.client.send(embed)

    def broadcast_complete(self, venture_id, campaign_id, outputs, elapsed):
        embed = {
            "title": f"🏁 PROTOCOL SECURED — {venture_id}",
            "color": 0x00C896,
            "fields": [
                {"name": "Jurisdiction", "value": f"Campaign #{campaign_id}", "inline": True},
                {"name": "Duration", "value": f"{elapsed}s", "inline": True},
                {"name": "Status", "value": "✅ Output Verified & Archived"}
            ],
            "footer": {"text": "LimesOutpost Outpost // Signal Division"}
        }
        self.client.send(embed)

    def broadcast_violation(self, venture_id, step_id, error_msg):
        embed = {
            "title": f"❌ CONTRACT VIOLATION — {venture_id}",
            "color": 0xFF4444,
            "fields": [
                {"name": "Breach Point", "value": f"`{step_id}`", "inline": True},
                {"name": "Ruling", "value": f"```{error_msg[:300]}```"}
            ],
            "footer": {"text": "LimesOutpost Outpost // Enforcement Division"}
        }
        self.client.send(embed)

    def broadcast_item_queued(self, venture_id, asset_type, title, campaign_id):
        emoji = "🎬" if "video" in asset_type.lower() else "📄"
        embed = {
            "title": f"📋 NEW ITEM QUEUED — {venture_id}",
            "color": 0xF5A623,
            "fields": [
                {"name": "Asset", "value": f"{emoji} {asset_type}", "inline": True},
                {"name": "Campaign", "value": f"#{campaign_id}", "inline": True},
                {"name": "Manifest", "value": f"**{title}**"}
            ],
            "footer": {"text": "LimesOutpost Outpost // Archivist Division"}
        }
        self.client.send(embed)