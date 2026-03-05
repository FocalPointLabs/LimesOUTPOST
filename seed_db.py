# seed_db.py
"""
LimesOutpost DB seeder.

Usage:
    python seed_db.py              # seeds all ventures in /ventures (except default)
    python seed_db.py yoga-zen-001 # seeds a specific venture folder

What it does per venture:
  1. Upserts the venture row in DB from brand_profile_v1.json
  2. Scaffolds pipeline_config.json if missing (minimal workflow toggles)
  3. Ensures brand_profile_v1.json has an identity.tts_voice_id block
  4. Runs migrations/init.sql to ensure schema is up to date
"""

import psycopg2
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Default ElevenLabs voice ID (Rachel) - works in dry run without a real key
DEFAULT_TTS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

# Minimal pipeline config — orchestrator merges this with ventures/default/
DEFAULT_PIPELINE_CONFIG = {
    "workflows": {
        "short_form_video": {"enabled": True},
        "blog_post":        {"enabled": True},
        "social_post":      {"enabled": True},
    }
}


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "limes_outpost_db"),
        user=os.getenv("DB_USER", "limes_outpost_user"),
        password=os.getenv("DB_PASSWORD", "limes_outpost_password"),
        port=os.getenv("DB_PORT", "5432"),
    )


def run_migrations(conn):
    """Ensures schema is up to date by running init.sql."""
    migration_path = Path("migrations/init.sql")
    if not migration_path.exists():
        print("⚠️  migrations/init.sql not found — skipping schema check.")
        return
    sql = migration_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("✅ Schema up to date.")


def scaffold_venture_files(venture_dir: Path, brand_json: dict):
    """
    Ensures the venture directory has all required files:
      - brand_profile_v1.json with identity block
      - pipeline_config.json with workflow toggles
    """
    venture_dir.mkdir(parents=True, exist_ok=True)

    # Ensure identity.tts_voice_id exists in brand profile
    if "identity" not in brand_json:
        brand_json["identity"] = {"tts_voice_id": DEFAULT_TTS_VOICE_ID}
        profile_path = venture_dir / "brand_profile_v1.json"
        profile_path.write_text(json.dumps(brand_json, indent=2), encoding="utf-8")
        print(f"   📝 Added identity.tts_voice_id to brand_profile_v1.json")

    # Scaffold pipeline_config.json if missing
    config_path = venture_dir / "pipeline_config.json"
    if not config_path.exists():
        config_path.write_text(json.dumps(DEFAULT_PIPELINE_CONFIG, indent=2), encoding="utf-8")
        print(f"   📝 Created pipeline_config.json")
    else:
        print(f"   ✓  pipeline_config.json exists")


def seed_venture(venture_folder: str, conn):
    """Synchronizes a specific venture folder's profile with the database."""
    venture_dir  = Path("ventures") / venture_folder
    profile_path = venture_dir / "brand_profile_v1.json"

    if not profile_path.exists():
        print(f"❌ Error: Could not find profile at {profile_path}")
        return

    with open(profile_path, "r", encoding="utf-8") as f:
        brand_json = json.load(f)

    venture_id = brand_json.get("venture_id")
    if not venture_id:
        print(f"❌ Error: 'venture_id' field missing from {profile_path}")
        return

    venture_name = brand_json.get("name")
    if not venture_name:
        print(f"❌ Error: 'name' field missing from {profile_path}. Add a top-level \"name\" key before seeding.")
        return

    print(f"\n🌱 Seeding: [{venture_name}] (id: {venture_id})")

    # Scaffold any missing files
    scaffold_venture_files(venture_dir, brand_json)

    # Build workflow_schedule from pipeline_config.json enabled flags
    config_path = venture_dir / "pipeline_config.json"
    workflow_schedule = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            default_crons = {
                "short_form_video": "0 9 * * *",
                "blog_post":        "0 10 * * 1",
                "social_post":      "0 12 * * *",
                "email":            "0 8 * * *",
                "analytics":        "0 6 * * *",
                "social_reply":     "0 12 * * *",
            }
            for wf_name, wf_cfg in config.get("workflows", {}).items():
                workflow_schedule[wf_name] = {
                    "enabled": wf_cfg.get("enabled", True),
                    "cron":    default_crons.get(wf_name, "0 9 * * *"),
                }
        except Exception as e:
            print(f"   ⚠️  Could not parse pipeline_config.json: {e}")

    # Upsert venture into DB
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO public.ventures (id, name, brand_profile, workflow_schedule)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name              = EXCLUDED.name,
                brand_profile     = EXCLUDED.brand_profile,
                workflow_schedule = EXCLUDED.workflow_schedule;
        """, (
            venture_id,
            venture_name,
            json.dumps(brand_json),
            json.dumps(workflow_schedule),
        ))
    conn.commit()
    print(f"   ✅ Venture '{venture_id}' synchronized.")


if __name__ == "__main__":
    try:
        conn = get_conn()
    except Exception as e:
        print(f"❌ Could not connect to DB: {e}")
        sys.exit(1)

    # Run migrations first
    run_migrations(conn)

    if len(sys.argv) > 1:
        seed_venture(sys.argv[1], conn)
    else:
        print("\n🔍 Scanning /ventures directory...")
        ventures_root = Path("ventures")
        if ventures_root.exists():
            folders = [
                f for f in ventures_root.iterdir()
                if f.is_dir() and f.name != "default"
            ]
            if not folders:
                print("   No venture folders found.")
            for folder in sorted(folders):
                seed_venture(folder.name, conn)

    conn.close()
    print("\n🎉 Seeding complete.")