-- =============================================================
-- LimesOutpost — Complete Database Initialisation
-- =============================================================
-- Single source of truth. Safe to run on a fresh DB or re-run
-- against an existing one (all statements use IF NOT EXISTS).
--
-- Table creation order (dependency chain):
--   users → ventures → venture_members
--   ventures → campaigns → content_items → assets
--   assets → publish_queue
--   assets → analytics_events
--   ventures → market_intel
--   ventures → email_threads
--   ventures → social_mentions
--   ventures → pulse_reports
-- =============================================================


-- -------------------------------------------------------------
--  users
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.users (
    id            uuid DEFAULT gen_random_uuid() NOT NULL,
    email         text NOT NULL,
    password_hash text NOT NULL,
    created_at    timestamp with time zone DEFAULT NOW(),
    last_login    timestamp with time zone,
    CONSTRAINT users_pkey         PRIMARY KEY (id),
    CONSTRAINT users_email_unique UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_users_email
    ON public.users (email);


-- -------------------------------------------------------------
--  ventures
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.ventures (
    id                text    NOT NULL,
    name              text    NOT NULL,
    brand_profile     jsonb   NOT NULL,
    status            text    NOT NULL DEFAULT 'active',
    workflow_schedule jsonb   NOT NULL DEFAULT '{}',
    timezone          text    NOT NULL DEFAULT 'UTC',
    user_id           uuid    REFERENCES public.users(id) ON DELETE SET NULL,
    whitelisted_emails text[] DEFAULT '{}'::text[],
    tts_voice_id      text    DEFAULT '21m00Tcm4TlvDq8ikWAM', -- Added via manual schema update
    created_at        timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ventures_pkey         PRIMARY KEY (id),
    CONSTRAINT ventures_status_check CHECK (status IN ('active', 'paused', 'archived'))
);

CREATE INDEX IF NOT EXISTS idx_ventures_status
    ON public.ventures (status);

CREATE INDEX IF NOT EXISTS idx_ventures_user
    ON public.ventures (user_id);


-- -------------------------------------------------------------
--  venture_members
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.venture_members (
    user_id    uuid NOT NULL,
    venture_id text NOT NULL,
    role       text NOT NULL DEFAULT 'operator',
    joined_at  timestamp with time zone DEFAULT NOW(),
    CONSTRAINT venture_members_pkey
        PRIMARY KEY (user_id, venture_id),
    CONSTRAINT venture_members_user_fkey
        FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE,
    CONSTRAINT venture_members_venture_fkey
        FOREIGN KEY (venture_id) REFERENCES public.ventures(id) ON DELETE CASCADE,
    CONSTRAINT venture_members_role_check
        CHECK (role IN ('operator', 'viewer'))
);

CREATE INDEX IF NOT EXISTS idx_venture_members_user
    ON public.venture_members (user_id);

CREATE INDEX IF NOT EXISTS idx_venture_members_venture
    ON public.venture_members (venture_id);


-- -------------------------------------------------------------
--  campaigns
-- -------------------------------------------------------------

CREATE SEQUENCE IF NOT EXISTS public.campaigns_id_seq
    START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS public.campaigns (
    id         integer DEFAULT nextval('public.campaigns_id_seq') NOT NULL,
    venture_id text,
    niche      text NOT NULL,
    status     text DEFAULT 'active',
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    metadata   jsonb,
    CONSTRAINT campaigns_pkey PRIMARY KEY (id),
    CONSTRAINT campaigns_venture_id_fkey
        FOREIGN KEY (venture_id) REFERENCES public.ventures(id)
);


-- -------------------------------------------------------------
--  content_items
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.content_items (
    id              text    NOT NULL,
    campaign_id     integer,
    sequence_number integer,
    topic           text,
    script_data     jsonb,
    assets          jsonb,
    status          text DEFAULT 'pending',
    error_message   text,
    created_at      timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    metadata        jsonb,
    CONSTRAINT content_items_pkey PRIMARY KEY (id),
    CONSTRAINT content_items_campaign_id_fkey
        FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id)
);

CREATE INDEX IF NOT EXISTS idx_content_campaign
    ON public.content_items USING btree (campaign_id);

CREATE INDEX IF NOT EXISTS idx_content_status
    ON public.content_items USING btree (status);


-- -------------------------------------------------------------
--  assets
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.assets (
    id              uuid DEFAULT gen_random_uuid() NOT NULL,
    content_item_id text,
    file_path       text NOT NULL,
    file_type       text,
    metadata        jsonb,
    venture_id      text REFERENCES public.ventures(id),
    status          text DEFAULT 'pending_review',
    asset_type      text,
    platform        text,
    created_at      timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT assets_pkey         PRIMARY KEY (id),
    CONSTRAINT unique_content_item UNIQUE (content_item_id),
    CONSTRAINT assets_content_item_id_fkey
        FOREIGN KEY (content_item_id) REFERENCES public.content_items(id)
);


-- -------------------------------------------------------------
--  publish_queue
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.publish_queue (
    id               uuid DEFAULT gen_random_uuid() NOT NULL,
    asset_id         uuid,
    venture_id       text NOT NULL,
    platform         text NOT NULL DEFAULT 'youtube',
    status           text NOT NULL DEFAULT 'pending_review',
    title            text,
    description      text,
    tags             text[],
    scheduled_for    timestamp with time zone,
    approved_at      timestamp with time zone,
    published_at     timestamp with time zone,
    platform_post_id text,
    platform_url     text,
    error_message    text,
    retry_count      integer DEFAULT 0,
    created_at       timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at       timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT publish_queue_pkey PRIMARY KEY (id),
    CONSTRAINT publish_queue_asset_fkey
        FOREIGN KEY (asset_id) REFERENCES public.assets(id),
    CONSTRAINT publish_queue_status_check CHECK (
        status IN (
            'pending_review', 'approved', 'rejected',
            'publishing', 'published', 'failed'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_publish_queue_status
    ON public.publish_queue (status);

CREATE INDEX IF NOT EXISTS idx_publish_queue_venture
    ON public.publish_queue (venture_id);

CREATE INDEX IF NOT EXISTS idx_publish_queue_scheduled
    ON public.publish_queue (scheduled_for)
    WHERE status = 'approved';


-- -------------------------------------------------------------
--  market_intel
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.market_intel (
    id         uuid DEFAULT gen_random_uuid() NOT NULL,
    venture_id text NOT NULL,
    intel_type text,
    content    text,
    metadata   jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT market_intel_pkey PRIMARY KEY (id)
);


-- -------------------------------------------------------------
--  email_threads
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.email_threads (
    id               uuid DEFAULT gen_random_uuid() NOT NULL,
    venture_id       text NOT NULL,
    gmail_thread_id  text NOT NULL,
    gmail_message_id text NOT NULL,
    sender_email     text NOT NULL,
    sender_name      text,
    subject          text,
    body_snippet     text,
    full_thread_json jsonb,
    category         text,
    priority_score   integer,
    is_whitelisted   boolean DEFAULT false,
    triage_notes     text,
    status           text NOT NULL DEFAULT 'fetched',
    created_at       timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at       timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT email_threads_pkey               PRIMARY KEY (id),
    CONSTRAINT email_threads_gmail_thread_unique UNIQUE (gmail_thread_id),
    CONSTRAINT email_threads_status_check CHECK (
        status IN ('fetched', 'triaged', 'drafted', 'sent', 'ignored')
    ),
    CONSTRAINT email_threads_category_check CHECK (
        category IS NULL OR category IN ('urgent', 'normal', 'low', 'ignore')
    )
);

CREATE INDEX IF NOT EXISTS idx_email_threads_venture
    ON public.email_threads (venture_id);

CREATE INDEX IF NOT EXISTS idx_email_threads_status
    ON public.email_threads (status);

CREATE INDEX IF NOT EXISTS idx_email_threads_sender
    ON public.email_threads (sender_email);

CREATE INDEX IF NOT EXISTS idx_email_threads_priority
    ON public.email_threads (priority_score DESC)
    WHERE status = 'triaged';


-- -------------------------------------------------------------
--  social_mentions
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.social_mentions (
    id              uuid DEFAULT gen_random_uuid() NOT NULL,
    venture_id      text NOT NULL,
    platform        text NOT NULL DEFAULT 'twitter',
    mention_id      text NOT NULL,
    conversation_id text,
    in_reply_to_id  text,
    author_username text,
    author_id       text,
    text            text,
    is_whitelisted  boolean DEFAULT false,
    category        text,
    priority_score  integer,
    triage_notes    text,
    status          text NOT NULL DEFAULT 'fetched',
    created_at      timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at      timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT social_mentions_pkey                   PRIMARY KEY (id),
    CONSTRAINT social_mentions_platform_mention_unique UNIQUE (platform, mention_id),
    CONSTRAINT social_mentions_status_check CHECK (
        status IN ('fetched', 'triaged', 'drafted', 'replied', 'ignored')
    ),
    CONSTRAINT social_mentions_category_check CHECK (
        category IS NULL OR category IN ('urgent', 'normal', 'low', 'ignore')
    )
);

CREATE INDEX IF NOT EXISTS idx_social_mentions_venture
    ON public.social_mentions (venture_id);

CREATE INDEX IF NOT EXISTS idx_social_mentions_status
    ON public.social_mentions (status);

CREATE INDEX IF NOT EXISTS idx_social_mentions_priority
    ON public.social_mentions (priority_score DESC)
    WHERE status = 'triaged';


-- -------------------------------------------------------------
--  analytics_events
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.analytics_events (
    id           uuid DEFAULT gen_random_uuid() NOT NULL,
    venture_id   text NOT NULL,
    asset_id     uuid,
    platform     text NOT NULL,
    metric_type  text NOT NULL,
    metric_value numeric,
    recorded_at  timestamp with time zone NOT NULL,
    created_at   timestamp with time zone DEFAULT NOW(),
    metadata     jsonb,
    CONSTRAINT analytics_events_pkey PRIMARY KEY (id),
    CONSTRAINT analytics_events_venture_fkey
        FOREIGN KEY (venture_id) REFERENCES public.ventures(id) ON DELETE CASCADE,
    CONSTRAINT analytics_events_asset_fkey
        FOREIGN KEY (asset_id) REFERENCES public.assets(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_analytics_venture
    ON public.analytics_events (venture_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_asset
    ON public.analytics_events (asset_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_platform
    ON public.analytics_events (platform, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_metric_type
    ON public.analytics_events (metric_type, metric_value DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_recorded
    ON public.analytics_events (recorded_at DESC);


-- -------------------------------------------------------------
--  pulse_reports
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.pulse_reports (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    venture_id text NOT NULL REFERENCES public.ventures(id) ON DELETE CASCADE,
    stats      jsonb NOT NULL DEFAULT '{}',
    briefing   text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS pulse_reports_venture_created
    ON public.pulse_reports (venture_id, created_at DESC);


-- -------------------------------------------------------------
--  Backup tables
-- -------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.assets_backup (
    id uuid, content_item_id text, file_path text,
    file_type text, metadata jsonb,
    created_at timestamp with time zone
);

CREATE TABLE IF NOT EXISTS public.content_items_backup (
    id text, 
    campaign_id text, 
    sequence_number integer,
    topic text, 
    script_data jsonb, 
    assets jsonb,
    status text, 
    error_message text, 
    created_at timestamp with time zone
);