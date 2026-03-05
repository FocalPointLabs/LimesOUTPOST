import os
from datetime import datetime
from limes_outpost.utils.dry_run import dry_run_enabled
from dotenv import load_dotenv
from limes_outpost.utils.validator import ContractValidator
from limes_outpost.utils.llm_client import LLMClient
from limes_outpost.utils.logger import LimesOutpostLogger

load_dotenv()


class BaseAgent:
    """
    Base class for all LimesOutpost agents.

    Services injection
    ------------------
    Agents that require shared stateful resources (e.g. a database connection
    pool) receive them through the `services` dict rather than as individual
    constructor arguments. This keeps constructor signatures stable as new
    services are added over time.

    Current canonical service keys
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        "db_pool"   — psycopg2 SimpleConnectionPool owned by the Orchestrator.
                      Agents that perform DB reads/writes should access it via
                      self.get_service("db_pool").

    Stateless utilities (LLMClient, ContractValidator) are still instantiated
    directly on BaseAgent because every agent that uses them wants the same
    default instance and there is no benefit to sharing a single copy.

    Usage in a subclass
    ~~~~~~~~~~~~~~~~~~~
        class MyAgent(BaseAgent):
            def __init__(self, services=None):
                super().__init__(agent_id="my_agent", services=services)

        # Accessing a service inside a method:
        db_pool = self.get_service("db_pool")
    """

    def __init__(self, agent_id, services=None):
        self.agent_id = agent_id
        self.services = services or {}
        self.validator = ContractValidator()
        self.llm = LLMClient()
        self.logger = LimesOutpostLogger()

    # ------------------------------------------------------------------
    # Services helpers
    # ------------------------------------------------------------------

    def get_service(self, key):
        """Returns the requested service, or None if it was not injected.

        Prefer this over direct dict access so call sites don't need to
        guard against self.services being None.

        Usage:
            db_pool = self.get_service("db_pool")
            if not db_pool:
                return {"status": "error", "message": "No DB pool available."}
        """
        return self.services.get(key)

    # ------------------------------------------------------------------
    # Envelope / metadata helpers
    # ------------------------------------------------------------------

    def create_envelope(self, task_input, brand_snapshot):
        """Wraps the task in the 'LimesOutpost Envelope' for LLM context."""
        is_dry_run = dry_run_enabled()

        envelope = {
            "agent_id": self.agent_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "control_block": {
                "dry_run": is_dry_run,
                "provider_priority": ["openai", "elevenlabs", "kling"],
                "approval_requirement": "manual_review"
            },
            "brand_profile_snapshot": brand_snapshot,
            "input_data": task_input
        }
        return envelope

    def _inject_metadata(self, result, brand_snapshot):
        """Injects standard top-level fields into every agent output dict."""
        if not isinstance(result, dict):
            return result

        result["venture_id"] = (
            brand_snapshot.get("venture_id") or
            brand_snapshot.get("name") or
            "default_venture"
        )

        result["niche_focus"] = (
            brand_snapshot.get("niche") or
            brand_snapshot.get("category") or
            "General"
        )

        return result

    def validate_result(self, data, contract_name):
        """Standard exit gate for all agents using external JSON contracts."""
        try:
            self.validator.check(data, contract_name)
            return data
        except Exception as e:
            self.logger.error(f"❌ CONTRACT BREACH in [{contract_name}]: {e}")
            raise

    def dry_run(self, task_input, brand_snapshot):
        raise NotImplementedError("Each agent must define its own dry_run fallback.")

    def live_run(self, task_input, brand_snapshot):
        raise NotImplementedError("Each agent must define its own live_run logic.")

    # ------------------------------------------------------------------
    # Context helpers — use these in every agent instead of raw dict access
    # ------------------------------------------------------------------

    def get_brand(self, context):
        """Returns the brand snapshot regardless of how context was passed.

        The orchestrator passes brand_snapshot as context directly (flat).
        Some legacy call sites pass it nested under 'brand_snapshot'.
        This method handles both so agents never need to care.

        Usage:
            brand = self.get_brand(context)
        """
        if not isinstance(context, dict):
            return {}
        # Flat shape (orchestrator standard): context IS the brand snapshot
        if "venture_id" in context:
            return context
        # Nested shape (legacy): context wraps brand_snapshot under a key
        return context.get("brand_snapshot", context)

    def get_venture_id(self, context):
        """Returns venture_id from context regardless of shape.

        Usage:
            venture_id = self.get_venture_id(context)
        """
        brand = self.get_brand(context)
        return brand.get("venture_id") or context.get("venture_id", "unknown")

    def unwrap_input(self, input_data, key):
        """Unwraps a nested agent output if the given key is present.

        Agents return a wrapper dict (e.g. {"status": "success", "blog_strategy_output": {...}}).
        The orchestrator stores the full wrapper in global_context, so the next agent
        receives the wrapper as input_data. This method extracts the inner payload
        cleanly without the receiving agent needing to know the wrapper shape.

        Returns the inner payload if key exists, otherwise returns input_data as-is
        so direct calls (e.g. in tests) still work without wrapping.

        Usage:
            brief = self.unwrap_input(input_data, "blog_strategy_output")
        """
        if isinstance(input_data, dict) and key in input_data:
            return input_data[key]
        return input_data