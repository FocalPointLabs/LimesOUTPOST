# pulse_agent.py
import json
from limes_outpost.agents.base_agent import BaseAgent
from limes_outpost.integrations.discord import OutpostSignalClient
from limes_outpost.integrations.channel_adapter import LimesOutpostAdapter

class PulseAgent(BaseAgent):
    def __init__(self, services=None):
        super().__init__(agent_id="pulse_briefing", services=services)

    def get_factory_stats(self, venture_id=None):
        """Queries live metrics based on schema.sql."""
        db_pool = self.get_service("db_pool")
        if not db_pool:
            return {"recent_renders": 0, "failed_contracts": 0, "total_tracked_items": 0}

        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                if venture_id:
                    cur.execute("""
                        SELECT
                            COUNT(*) as total,
                            COUNT(*) FILTER (WHERE ci.status = 'completed') as success,
                            COUNT(*) FILTER (WHERE ci.status = 'failed') as failures
                        FROM public.content_items ci
                        JOIN public.campaigns c ON c.id = ci.campaign_id
                        WHERE ci.created_at > NOW() - INTERVAL '24 hours'
                          AND c.venture_id = %s;
                    """, (venture_id,))
                else:
                    cur.execute("""
                        SELECT
                            COUNT(*) as total,
                            COUNT(*) FILTER (WHERE status = 'completed') as success,
                            COUNT(*) FILTER (WHERE status = 'failed') as failures
                        FROM public.content_items
                        WHERE created_at > NOW() - INTERVAL '24 hours';
                    """)
                row = cur.fetchone()
                return {
                    "recent_renders":     row[1] or 0,
                    "failed_contracts":   row[2] or 0,
                    "total_tracked_items": row[0] or 0,
                }
        finally:
            db_pool.putconn(conn)

    def run(self, input_data, context, campaign_id=None):
        """Standard entry point called by orchestrator."""
        venture_id = context.get("venture_id") if context else None
        stats = self.get_factory_stats(venture_id=venture_id)
        
        # Calculate Health %
        total = stats['total_tracked_items']
        success_rate = (stats['recent_renders'] / total * 100) if total > 0 else 100.0
        
        briefing_insight = self.generate_assistant_briefing(context, stats, success_rate)

        output = f"""LIMES_OUTPOST ASSISTANT: PULSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 SYSTEM HEALTH: {success_rate:.1f}%
⚠️ BLOCKERS: {stats['failed_contracts']} active issues
🤖 ASSISTANT BRIEF:
{briefing_insight}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

        # Persist to DB so the dashboard can surface it
        self._save_report(venture_id=venture_id, stats=stats, briefing=output)

        # --- NEW: Outpost Signal Hook ---
        try:
            signal = OutpostSignalClient()
            adapter = LimesOutpostAdapter(signal)
            adapter.broadcast_pulse(
                venture_id=venture_id,
                stats=stats,
                briefing_text=output # This is the formatted string from your agent
            )
        except Exception as e:
            self.logger.warning(f"⚠️ Pulse Signal failed to broadcast: {e}")

        return {"briefing_text": output, "stats": stats}

    def generate_assistant_briefing(self, context, stats, success_rate):
        brand = self.get_brand(context) if context else {}
        system_role = f"""
        You are the LimesOutpost Assistant, a high-level strategic advisor for {brand.get('name', 'the brand')}.
        Your tone is 'Millionaire Founder'—sharp, efficient, and obsessed with growth.
        You don't just list numbers; you interpret them into actionable insights.
        """
        
        user_prompt = f"""
        SITUATION REPORT:
        - Niche: {brand.get('niche', 'Wellness')}
        - System Health: {success_rate:.1f}%
        - Failed Steps: {stats['failed_contracts']}
        - System Load: {stats['total_tracked_items']} units produced in last 24h
        
        TASK: Give a 2-sentence briefing as my assistant.
        If failures > 0: Be urgent and identify that the pipeline has friction that needs clearing.
        If health is 100%: Be aggressive about scaling or dominant strategy for the {brand.get('niche', 'Wellness')} market.
        """
        return self.llm.generate(system_role, user_prompt, json_mode=False)

    def _save_report(self, venture_id, stats, briefing):
        """Persists the pulse report to public.pulse_reports."""
        if not venture_id: return
        db_pool = self.get_service("db_pool")
        if not db_pool: return
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.pulse_reports (venture_id, stats, briefing)
                    VALUES (%s, %s, %s);
                """, (venture_id, json.dumps(stats), briefing))
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            db_pool.putconn(conn)