// types/index.ts
// Mirrors the Pydantic schemas from limes_outpost/api/schemas/__init__.py

// ── Auth ──────────────────────────────────────────────────────
export interface TokenResponse {
  access_token:  string;
  refresh_token: string;
  token_type:    string;
}

export interface User {
  id:         string;
  email:      string;
  created_at: string;
}

// ── Ventures ──────────────────────────────────────────────────
export interface WorkflowScheduleEntry {
  cron:    string;
  enabled: boolean;
}

export interface WorkflowSchedule {
  short_form_video?: WorkflowScheduleEntry;
  blog_post?:        WorkflowScheduleEntry;
  email?:            WorkflowScheduleEntry;
  social_reply?:     WorkflowScheduleEntry;
  analytics?:        WorkflowScheduleEntry;
  [key: string]:     WorkflowScheduleEntry | undefined;
}

export interface Venture {
  id:                string;
  name:              string;
  brand_profile:     Record<string, unknown>;
  status:            "active" | "paused" | "archived";
  workflow_schedule: WorkflowSchedule;
  timezone:          string;
  role:              "operator" | "viewer";
}

export interface VentureCreateRequest {
  id:            string;
  name:          string;
  brand_profile: Record<string, unknown>;
  timezone?:     string;
}

export interface VenturePatchRequest {
  name?:              string;
  brand_profile?:     Record<string, unknown>;
  workflow_schedule?: WorkflowSchedule;
  timezone?:          string;
  status?:            string;
}

// ── Queue ─────────────────────────────────────────────────────
export type QueueStatus =
  | "pending_review"
  | "approved"
  | "rejected"
  | "publishing"
  | "published"
  | "failed";

export interface QueueItem {
  id:            string;
  venture_id:    string;
  platform:      string;
  status:        QueueStatus;
  title:         string | null;
  description:   string | null;
  tags:          string[] | null;
  created_at:    string;
  scheduled_for: string | null;
}

export interface QueuePatchRequest {
  action:        "approve" | "reject" | "edit";
  title?:        string;
  description?:  string;
  tags?:         string[];
  scheduled_for?: string;
  reason?:       string;
}

// ── Pipeline ──────────────────────────────────────────────────
export type PipelineStatus = "pending" | "running" | "completed" | "failed";

export interface PipelineStep {
  step_id:    string;
  topic:      string;
  status:     string;
  created_at: string;
}

export interface PipelineProgress {
  campaign_id: number;
  venture_id:  string;
  steps:       PipelineStep[];
  overall:     PipelineStatus;
}

export interface PipelineRunRequest {
  topic?:       string;
  campaign_id?: number;
}

export interface PipelineRunResponse {
  campaign_id: number | null;
  task_id:     string;
  status:      string;
}

// ── Analytics ─────────────────────────────────────────────────
export interface AnalyticsSummary {
  venture_id:   string;
  platform:     string;
  total_views:  number | null;
  total_likes:  number | null;
  avg_ctr:      number | null;
  top_asset_id: string | null;
  as_of:        string | null;
}

// ── WebSocket messages ────────────────────────────────────────
export interface WsPipelineMessage {
  campaign_id: number;
  venture_id:  string;
  steps:       PipelineStep[];
  overall:     PipelineStatus;
}
