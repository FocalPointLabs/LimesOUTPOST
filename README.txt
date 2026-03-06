# LimesOUTPOST

_
      _  //  _
     (_)//  (_)
   .-'         '-.
  /    \  |  /    \
 /  \   \ | /   /  \
|    \   \|/   /    |
|----- > ( ) < -----|
|    /   /|\   \    |
 \  /   / | \   \  /
  \    /  |  \    /
   '- ._______.-' 

**An open source agentic content platform. Run your own outpost.**

LimesOUTPOST is a self-hosted brand aware AI content factory that handles the full production loop from market research to strategy, scripting, voiceover, video, blog, newsletter and socials from a single input, with a human approval step before anything goes live. Then publish across platforms with one button. Limes also monitors your Gmail, categorizes your inbox, and writes auto replies to approved whitelist, keeping all others in draft. The built in strategy room has a chatbot that preloads your venture profiles to assist in your process. Daily reports sent as notifications to your Discord channel. 

The name comes from the Roman *limes* — the frontier fortification system. A network of independent outposts, each locally commanded, connected by shared roads and shared standards. That's the idea here. You run your own outpost. Your data, your brand, your workflows, your call on what goes out.

---

## The Philosophy

Every workflow has a human checkpoint before publish. You get the leverage of an AI production team without handing over the keys just yet. In updates, the autonomy dial will be yours to set.

Brand identity is a first-class citizen. Every agent in the pipeline works from your brand profile using your voice, your tone, your approved vocabulary, your visual style. The system can't drift from the venture profiles they're the foundation everything is built on.

---

## What It Does

One command (or one button in the UI) kicks off a full production cycle:

```
Intel → Strategy → Script → Voiceover → Video → Blog → Social
                                    ↓
                          Unified Approval Queue
                                    ↓
                    YouTube · Twitter/X · Gmail · Discord
```

- **Market Intel** — scans news and trends relevant to your niche
- **Strategy** — builds a content angle from the intel
- **Script** — writes the video script and blog outline
- **Voiceover** — synthesizes audio via ElevenLabs
- **Video** — generates scenes via Kling AI, composes via Creatomate
- **Blog** — writes and formats a full article
- **Social** — drafts on-brand tweets
- **Review Queue** — approve, reject, or edit before anything publishes
- **Publishing** — YouTube, Twitter/X, Gmail, with Discord notifications
- **Analytics** — pulls YouTube performance data back into the loop
- **Daily Pulse** — AI-generated briefing on your content operation

---

## The Stack

```
limes_outpost/        Python package — all agents, pipelines, contracts
cli/                  CLI entry point
api/                  FastAPI on :8000 (Swagger at /docs)
worker/               Celery + Beat async execution
limes_outpost-web/    Next.js 16 dashboard
Postgres 15           source of truth for all pipeline state
Redis 7               Celery broker
Docker Compose        runs everything together
```

---

## Getting Started

### Prerequisites

- Docker Desktop
- Python 3.11+
- Node.js 18+
- API keys for the services you want to use (see below)

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/limes-outpost.git
cd limes-outpost
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```env
# Required
CEREBRAS_API_KEY=        # LLM inference (fast, generous free tier)
# ── DATABASE CREDENTIALS (Must match docker-compose.yml) ──────
# Use 'localhost' for local seeding, use 'db' if running inside Docker
DB_HOST=db
DB_PORT=5432
DB_NAME=limes_outpost_db
DB_USER=limes_outpost_user
DB_PASSWORD=limes_outpost_password

# Optional — enable the workflows you want
ELEVENLABS_API_KEY=      # Voiceover
KLING_ACCESS_KEY=        # Video generation
KLING_SECRET_KEY=
CREATOMATE_API_KEY=      # Video composition
NEWSDATA_API_KEY=        # Market intel
DISCORD_WEBHOOK_URL=     # Notifications

# DRY_RUN=True runs everything with mock data — no API costs
DRY_RUN=True
```
REDIS_URL=redis://redis:6379/0

JWT_SECRET=insert a random sting here
JWT_ACCESS_EXPIRE_MIN=60
JWT_REFRESH_EXPIRE_DAYS=30


### 3. Start the database

```bash
docker-compose up -d db
```

### 4. Install the Python package

```bash
pip install -e .
```

### 5. Seed your first venture

```bash
python seed_db.py
```

Or use the UI — the venture setup wizard handles this without touching the terminal.

### 6. Start everything

```bash
docker-compose up
```

This brings up Postgres, Redis, the Celery worker, and Beat scheduler together.

### 7. Start the API

```bash
uvicorn api.main:app --reload --port 8000
```

### 8. Start the frontend

```bash
cd  limes_outpost-web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — create a venture, configure your brand profile, and run your first pipeline.

---

## Dry Run Mode

Set `DRY_RUN=True` in `.env` to run the full pipeline with mock data. Every agent executes, every step logs, nothing hits a paid API. Good for testing your setup before spending credits.

---

## CLI Reference

```bash
python cli/main.py yoga-zen-001 "morning mobility"     # full autonomous cycle
python cli/main.py --manual yoga-zen-001 "topic"       # skip intel layer
python cli/main.py --review yoga-zen-001               # review queue
python cli/main.py --email yoga-zen-001                # email triage cycle
python cli/main.py --social-reply yoga-zen-001         # mention/reply cycle
python cli/main.py --scheduler yoga-zen-001            # publish approved items
python cli/main.py --pulse yoga-zen-001                # daily briefing
```

---

## Adding a Venture

Each venture is an independent brand profile — its own voice, niche, visual style, approved vocabulary, and pipeline config. Add a folder to `ventures/` with a `brand_profile_v1.json` and a `pipeline_config.json`, seed it, and the full suite runs for that brand.

The venture config is the soul of the system. Every agent reads from it. Every output is anchored to it.

---

## Project Structure

```
limes_outpost/
  agents/           all pipeline agents
  api/              FastAPI routers and schemas
  contracts/        JSON schema validation for every agent handoff
  tasks/            Celery task definitions
  utils/            logger, LLM client, dry run, DB pool
  config.py         pydantic-settings, all env vars in one place
cli/                CLI entry point
api/                FastAPI app entry point  
worker/             Celery worker entry point
limes_outpost-web/  Next.js dashboard
ventures/           your venture configs (gitignored)
contracts/          JSON schemas — the handshake between agents
migrations/         SQL migration files
```

---

## Roadmap

This is a living project. v1 is the foundation — the outpost is built and operational. What comes next depends on what the community needs.

Ideas already in motion:
- Discord two-way approval (tap to approve from your phone)
- Instagram and TikTok publishing
- Image generation integrated into the UI
- Multi-user venture teams
- More workflow types

---

## License

MIT — take it, use it, build on it, run your own outpost.

---

## Origin

Built in about a 10 days by one person with no real prior coding experience, free tier AI, and Notepad.

The goal is simple: give independent creators and small businesses the same content production leverage that large teams have, with a human meaningfully in the loop at every step.

The outpost is open. Come build something.

---

*"Every town needs a Sheriff."*