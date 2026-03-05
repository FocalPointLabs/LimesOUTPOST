import copy
import json
import os
import importlib
import time
import psycopg2
from psycopg2 import pool
from limes_outpost.utils.logger import LimesOutpostLogger
from limes_outpost.agents.storage_agent import StorageAgent
from limes_outpost.agents.visual_agent import VisualAgent

class LimesOutpostOrchestrator:
    def __init__(self, venture_id):
        self.venture_id = venture_id
        self.logger = LimesOutpostLogger()
        
        # 1. Database Connection Pool
        self._init_db_pool()
        
        # 2. State & Blueprint Loading
        self.brand_snapshot = self._load_brand_profile()
        self.pipeline_config = self._load_pipeline_config()
        
        # 3. Specialized Production Helpers
        # VisualAgent receives the db_pool via services for consistency with all
        # other agents, and to ensure DB access is available if ever needed.
        services = {"db_pool": self.db_pool}
        self.visual_worker = VisualAgent(services=services)
        self.storage_worker = StorageAgent(self.visual_worker)

    def run_production_pipeline(self, initial_input, campaign_id=None):
        if not campaign_id:
            campaign_id = self._register_campaign(initial_input)
        else:
            self._register_campaign(initial_input, campaign_id=campaign_id)

        shared_context = {
            "initial_query": initial_input,
            "venture_id": self.venture_id,
            "campaign_id": campaign_id
        }

        self.logger.info(f"🚀 Starting Production for Campaign: {campaign_id}")

        # --- PHASE 1: Shared steps (run once, feed all workflows) ---
        # shared_context is mutated in place here. After this block it contains
        # the intel_directive and any other shared phase outputs that all
        # workflows need as their starting point.
        shared_steps = self.pipeline_config.get("shared_phases", [])
        if shared_steps:
            self.logger.info("--- [SHARED PHASES] ---")
            result = self._run_steps(shared_steps, shared_context, campaign_id)
            if result and result.get("status") == "failed":
                return result
        
        # --- PHASE 2: Per-workflow pipelines ---
        workflows = self.pipeline_config.get("workflows", {})

        if not workflows:
            # Backwards compatibility: support old flat "short_form_video" config shape
            legacy_steps = self.pipeline_config.get("short_form_video", [])
            if not legacy_steps:
                self.logger.error("❌ No workflows or legacy pipeline found in config.")
                return {"status": "error", "message": "Missing pipeline config"}
            self.logger.warning("⚠️  Legacy pipeline config detected. Consider upgrading to v2.0.0 format.")
            return self._run_steps(legacy_steps, shared_context, campaign_id)

        # Workflows handled by dedicated Beat tasks — not run inside the pipeline
        SCHEDULER_WORKFLOWS = {"publish", "email_cycle", "email", "social_reply", "analytics"}

        final_outputs = {}
        for workflow_name, workflow_config in workflows.items():
            if workflow_name in SCHEDULER_WORKFLOWS:
                self.logger.info(f"⏭️  Workflow '{workflow_name}' is a scheduler task. Skipping in pipeline.")
                continue

            if not workflow_config.get("enabled", True):
                self.logger.info(f"⏭️  Workflow '{workflow_name}' is disabled. Skipping.")
                continue

            self.logger.info(f"--- [WORKFLOW: {workflow_name.upper()}] ---")
            steps = workflow_config.get("steps", [])
            if not steps:
                self.logger.warning(f"⚠️  Workflow '{workflow_name}' has no steps. Skipping.")
                continue

            # Each workflow gets a deep copy of shared_context so workflows are
            # fully isolated from each other. Neither can observe or corrupt the
            # other's step outputs, regardless of key naming.
            workflow_context = copy.deepcopy(shared_context)

            result = self._run_steps(steps, workflow_context, campaign_id)
            if result and isinstance(result, dict) and result.get("status") == "failed":
                self.logger.error(f"❌ Workflow '{workflow_name}' failed at step: {result.get('last_step')}")
                # Log failure but continue to remaining workflows rather than aborting everything
                final_outputs[workflow_name] = result
                continue

            # Store the final output key from the last step of this workflow
            final_step_key = steps[-1]["output_key"]
            final_outputs[workflow_name] = workflow_context.get(final_step_key)
            self.logger.info(f"✅ Workflow '{workflow_name}' complete.")

        # --- POST-PIPELINE: Archive assets + enqueue for publish review ---
        self.logger.info("--- [ARCHIVING] ---")
        from limes_outpost.agents.archivist_agent import ArchivistAgent
        archivist = ArchivistAgent(services={"db_pool": self.db_pool})
        archive_result = archivist.run(
            input_data={"campaign_id": campaign_id},
            context=self.brand_snapshot,
            campaign_id=campaign_id
        )
        self.logger.info(archive_result.get("summary", "Archiving complete."))

        return final_outputs

    def _run_steps(self, steps, global_context, campaign_id):
        """Executes a list of steps in sequence, mutating global_context in place."""
        for step in steps:
            step_id = step["step_id"]
            output_key = step["output_key"]

            self.logger.info(f"--- [PHASE: {step_id.upper()}] ---")

            try:
                # 1. Check Cache (Database)
                existing = self.get_existing_step_data(campaign_id, step_id)
                if existing:
                    self.logger.info(f"✨ Step {step_id} found in cache. Skipping.")
                    global_context[output_key] = existing
                    continue

                # 2. Resolve Inputs
                worker_input = self._map_inputs(step, global_context)

                # 3. Execute Agent
                result = self.execute_baton_pass(
                    step_config=step,
                    input_data=worker_input,
                    campaign_id=campaign_id
                )

                # 4. Safety Guard for NoneType or Error status
                if not result or (isinstance(result, dict) and result.get("status") == "error"):
                    raise Exception(f"Agent {step_id} failed or returned an error status.")

                # 5. INSTANT PERSISTENCE
                self._archive_step_data(campaign_id, step_id, result, status="processing")

                # 6. Production Logic (Polling/Waiting)
                processed_data = self._handle_async_assets(step_id, result)

                # 7. Save final success result to context and database
                global_context[output_key] = processed_data
                self._archive_step_data(campaign_id, step_id, processed_data, status="completed")
                self.logger.info(f"✅ {step_id} complete.")

            except Exception as e:
                self.logger.error(f"❌ Phase {step_id} failed: {e}")
                self._archive_step_data(campaign_id, step_id, {"error": str(e)}, status="failed")
                return {"status": "failed", "last_step": step_id}

        return None

    def _map_inputs(self, step, context):
        """Resolves agent input from the pipeline context."""
        if "required_inputs" in step:
            return {k: context.get(v) for k, v in step["required_inputs"].items()}

        input_key = step.get("input_key", "initial_query")
        input_data = context.get(input_key)

        extract_key = step.get("extract_key")
        if extract_key and isinstance(input_data, dict):
            extracted = input_data.get(extract_key)
            if extracted is None:
                self.logger.error(
                    f"❌ _map_inputs: extract_key '{extract_key}' not found in "
                    f"context['{input_key}']. Available keys: {list(input_data.keys())}"
                )
            return extracted

        return input_data

    def _handle_async_assets(self, step_id, result):
        """Standardizes outputs and manages long-running AI polling."""
        data = result
        if isinstance(result, dict):
            if "visual_output" in result: data = result["visual_output"]
            elif "vo_output" in result: data = result["vo_output"]

        if step_id == "visual_phase":
            self.logger.info("⏳ Visuals detected. Polling Kling...")
            data["scenes"] = self.storage_worker.poll_and_download(data)
        
        if step_id == "composition_phase":
            self.logger.info("🎬 Composition submitted. Polling Creatomate...")
            final_path = self.storage_worker.poll_and_download_render(data)
            data["local_video_path"] = final_path

        return data

    def execute_baton_pass(self, step_config, input_data, campaign_id):
        """Invokes the specific agent class for a pipeline step."""
        module_path = step_config["module"]
        class_name = step_config["agent_class"]

        if not self.db_pool:
            self.logger.error("❌ Cannot execute pipeline: DB pool is unavailable.")
            return None

        services = {
            "db_pool": self.db_pool,
        }

        try:
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)
            agent_instance = agent_class(services=services)

            self.logger.info(f"🤖 Invoking {class_name}...")

            return agent_instance.run(
                input_data=input_data,
                context=self.brand_snapshot,
                campaign_id=campaign_id
            )
        except Exception as e:
            self.logger.error(f"💥 Agent Execution Error at {class_name}: {e}")
            return None

    # --- Database Helpers ---
    def _init_db_pool(self):
        self.db_pool = None
        try:
            self.db_pool = psycopg2.pool.SimpleConnectionPool(
                1, 10,
                host=os.getenv("DB_HOST", "localhost"),
                database=os.getenv("DB_NAME", "limes_outpost_db"),
                user=os.getenv("DB_USER", "limes_outpost_user"),
                password=os.getenv("DB_PASSWORD", "limes_outpost_password"),
                port=os.getenv("DB_PORT", "5432")
            )
            self.logger.info("🗄️ Database Connection Pool initialized.")
        except Exception as e:
            self.logger.error(f"❌ DB Pool Failure: {e}")

    def _register_campaign(self, initial_input, campaign_id=None):
        conn = self.db_pool.getconn()
        if isinstance(initial_input, dict):
            topic_str = initial_input.get("production_prompt") or \
                        initial_input.get("target_niche") or "Auto-Campaign"
        else:
            topic_str = initial_input

        try:
            with conn.cursor() as cur:
                if campaign_id:
                    cur.execute("""
                        INSERT INTO campaigns (id, venture_id, niche, status)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING;
                    """, (campaign_id, self.venture_id, topic_str[:50], "active"))
                else:
                    cur.execute("""
                        INSERT INTO campaigns (venture_id, niche, status)
                        VALUES (%s, %s, %s)
                        RETURNING id;
                    """, (self.venture_id, topic_str[:50], "active"))
                    campaign_id = cur.fetchone()[0]
                conn.commit()
                return campaign_id
        finally:
            self.db_pool.putconn(conn)

    def get_existing_step_data(self, campaign_id, step_id):
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cur:
                content_item_id = f"{campaign_id}_{step_id}"
                cur.execute(
                    "SELECT script_data FROM content_items WHERE id = %s AND status = 'completed'",
                    (content_item_id,)
                )
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            self.db_pool.putconn(conn)

    def _archive_step_data(self, campaign_id, step_id, data, status="completed"):
        content_item_id = f"{campaign_id}_{step_id}"
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO public.content_items (id, campaign_id, topic, status, script_data)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET script_data = EXCLUDED.script_data, status = EXCLUDED.status;
                """, (content_item_id, campaign_id, step_id, status, json.dumps(data)))
                conn.commit()
        finally:
            self.db_pool.putconn(conn)

    def _load_brand_profile(self):
        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, brand_profile FROM public.ventures WHERE id = %s",
                    (self.venture_id,)
                )
                row = cur.fetchone()
                if row and row[1]:
                    venture_name, profile = row[0], row[1]
                    return {
                        "venture_id":      self.venture_id,
                        "name":            venture_name or self.venture_id,
                        "niche":           profile.get("niche") or profile.get("category") or "General",
                        "mission":         profile.get("mission", ""),
                        "target_audience": profile.get("target_audience") or profile.get("audience", "General"),
                        "narrative":       profile.get("narrative", {}),
                        "identity":        profile.get("identity", {}),
                        "visual":          profile.get("visual", {}),
                        "rules":           profile.get("rules", {}),
                        "audience":        profile.get("audience", {}),
                        "blog":            profile.get("blog", {}),
                    }
                return self._empty_brand_snapshot()
        except Exception as e:
            self.logger.error(f"❌ Brand Load Error: {e}")
            return self._empty_brand_snapshot()
        finally:
            self.db_pool.putconn(conn)

    def _empty_brand_snapshot(self):
        return {
            "venture_id":      self.venture_id,
            "name":            self.venture_id,
            "niche":           "General",
            "mission":         "",
            "target_audience": "General",
            "narrative":       {},
            "identity":        {},
            "visual":          {},
            "rules":           {},
            "audience":        {},
            "blog":            {},
        }

    def _load_pipeline_config(self):
        """Two-layer pipeline config loader.

        Layer 1 — Base (ventures/default/pipeline_config.json):
            Defines all canonical workflows and steps. Every venture inherits this.

        Layer 2 — Venture override (ventures/{venture_id}/pipeline_config.json):
            Declares only what differs. Three things a venture override can do:

            TOGGLE  — enable/disable an existing workflow:
                      {"workflows": {"blog_post": {"enabled": false}}}

            REPLACE — swap a workflow's full steps array:
                      {"workflows": {"short_form_video": {"extends": false, "steps": [...]}}}
                      "extends": false is REQUIRED when supplying a steps array.

            ADD     — define a workflow base doesn't know about:
                      {"workflows": {"podcast": {"enabled": true, "steps": [...]}}}

        If no venture override exists, base config is returned as-is.
        If no base config exists, falls back to legacy per-venture full config.
        """
        base  = self._load_config_file("ventures/default/pipeline_config.json")
        local = self._load_config_file(f"ventures/{self.venture_id}/pipeline_config.json")

        # No base: fall back to legacy behaviour (venture carries full config)
        if not base:
            if local:
                self.logger.warning(
                    f"⚠️  No base pipeline config found. Using venture-local config for "
                    f"'{self.venture_id}' as full config (legacy mode)."
                )
                return local
            self.logger.warning(
                f"⚠️  No pipeline config found for '{self.venture_id}' or default. "
                f"Returning empty config — OK for non-pipeline commands."
            )
            return {"workflows": {}, "shared_phases": []}

        # Base exists, no venture override: use base directly
        if not local:
            self.logger.info(
                f"📋 No venture override for '{self.venture_id}'. "
                f"Using base pipeline config."
            )
            return base

        # Both exist: merge
        merged = self._merge_pipeline_configs(base, local)
        self.logger.info(
            f"📋 Pipeline config loaded for '{self.venture_id}' "
            f"(base + venture override merged)."
        )
        return merged

    def _load_config_file(self, path):
        """Loads a JSON config file. Returns None if the file doesn't exist."""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:
            self.logger.error(f"❌ Failed to load config at '{path}': {e}")
            return None

    def _merge_pipeline_configs(self, base, override):
        """Merges a venture override onto the base config.

        Merge rules per workflow:
          TOGGLE  — no 'steps' key in override: inherited steps kept,
                    only 'enabled' is updated.
          REPLACE — 'extends': false + 'steps' in override: entire workflow
                    definition is replaced. 'extends': false is required to
                    make the replacement explicit and prevent silent drift.
          ADD     — workflow key not in base: added wholesale from override.

        shared_phases are always inherited from base — never overridden
        at the venture level.
        """
        merged = copy.deepcopy(base)

        for wf_name, wf_override in override.get("workflows", {}).items():

            if wf_name not in merged["workflows"]:
                # ADD: new workflow unknown to base
                self.logger.info(
                    f"📋 [Config] Venture adds workflow '{wf_name}' (not in base)."
                )
                merged["workflows"][wf_name] = copy.deepcopy(wf_override)
                continue

            base_wf = merged["workflows"][wf_name]

            if wf_override.get("extends") is False:
                # REPLACE: venture explicitly owns this workflow's full definition
                if "steps" not in wf_override:
                    self.logger.warning(
                        f"⚠️  [Config] Workflow '{wf_name}' has 'extends: false' but "
                        f"no 'steps' array. Falling back to base steps."
                    )
                    base_wf["enabled"] = wf_override.get("enabled", base_wf.get("enabled", True))
                else:
                    self.logger.info(
                        f"📋 [Config] Venture fully replaces workflow '{wf_name}' "
                        f"(extends: false)."
                    )
                    merged["workflows"][wf_name] = copy.deepcopy(wf_override)

            elif "steps" in wf_override:
                # GUARD: steps array without extends: false is a footgun —
                # log a loud warning and ignore the venture's steps array.
                self.logger.warning(
                    f"⚠️  [Config] Workflow '{wf_name}' in venture override has a "
                    f"'steps' array but no 'extends: false' flag. "
                    f"Steps array IGNORED — using base steps. "
                    f"Set 'extends: false' to explicitly replace, or remove "
                    f"'steps' to toggle only."
                )
                base_wf["enabled"] = wf_override.get("enabled", base_wf.get("enabled", True))

            else:
                # TOGGLE: no steps key — just update enabled flag
                if "enabled" in wf_override:
                    base_wf["enabled"] = wf_override["enabled"]

        return merged