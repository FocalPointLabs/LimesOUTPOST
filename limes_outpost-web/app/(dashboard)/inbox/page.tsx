"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, publishApi } from "@/lib/api";
import { useVentureStore } from "@/store";
import {
  Mail, RefreshCw, Shield, ShieldOff, Inbox,
  Clock, CheckCircle2, XCircle, Zap, Twitter,
  EyeOff, ExternalLink, ChevronDown, ChevronUp,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import toast from "react-hot-toast";

// ── Types ──────────────────────────────────────────────────────

interface EmailThread {
  id: string;
  gmail_thread_id: string;
  sender_email: string;
  sender_name: string;
  subject: string;
  body_snippet: string;
  category: "urgent" | "normal" | "low" | "ignore" | null;
  priority_score: number | null;
  is_whitelisted: boolean;
  triage_notes: string | null;
  status: "fetched" | "triaged" | "drafted" | "sent" | "ignored";
  created_at: string;
}

interface SocialMention {
  id: string;
  mention_id: string;
  platform: string;
  author_username: string;
  author_id: string;
  text: string;
  category: "urgent" | "normal" | "low" | "ignore" | null;
  priority_score: number | null;
  is_whitelisted: boolean;
  triage_notes: string | null;
  status: "fetched" | "triaged" | "drafted" | "ignored";
  created_at: string;
}

// ── Config ─────────────────────────────────────────────────────

const EMAIL_STATUS_CONFIG = {
  fetched:  { label: "Fetched",  icon: Inbox,        color: "text-ink-muted",  bg: "bg-elevated"    },
  triaged:  { label: "Triaged",  icon: Clock,         color: "text-warning",    bg: "bg-warning/10"  },
  drafted:  { label: "Drafted",  icon: Mail,          color: "text-accent",     bg: "bg-accent/10"   },
  sent:     { label: "Sent",     icon: CheckCircle2,  color: "text-success",    bg: "bg-success/10"  },
  ignored:  { label: "Ignored",  icon: XCircle,       color: "text-ink-muted",  bg: "bg-elevated"    },
};

const SOCIAL_STATUS_CONFIG = {
  fetched:  { label: "Fetched",  icon: Inbox,        color: "text-ink-muted",  bg: "bg-elevated"    },
  triaged:  { label: "Triaged",  icon: Clock,         color: "text-warning",    bg: "bg-warning/10"  },
  drafted:  { label: "Drafted",  icon: Twitter,       color: "text-accent",     bg: "bg-accent/10"   },
  ignored:  { label: "Ignored",  icon: XCircle,       color: "text-ink-muted",  bg: "bg-elevated"    },
};

const CATEGORY_CONFIG = {
  urgent: { label: "Urgent", color: "text-danger",    bg: "bg-danger/10"  },
  normal: { label: "Normal", color: "text-accent",    bg: "bg-accent/10"  },
  low:    { label: "Low",    color: "text-ink-muted", bg: "bg-elevated"   },
  ignore: { label: "Ignore", color: "text-ink-muted", bg: "bg-elevated"   },
};

const EMAIL_FILTERS   = ["all", "fetched", "triaged", "drafted", "sent", "ignored"] as const;
const SOCIAL_FILTERS  = ["all", "fetched", "triaged", "drafted", "ignored"] as const;

// ── Shared components ──────────────────────────────────────────

function PriorityBar({ score }: { score: number | null }) {
  if (!score) return null;
  const pct   = (score / 10) * 100;
  const color = score >= 8 ? "bg-danger" : score >= 5 ? "bg-warning" : "bg-ink-muted";
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1 rounded-full bg-elevated overflow-hidden">
        <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-ink-muted mono">{score}/10</span>
    </div>
  );
}

function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  const cfg = CATEGORY_CONFIG[category as keyof typeof CATEGORY_CONFIG];
  if (!cfg) return null;
  return (
    <span className={cn("text-xs px-1.5 py-0.5 rounded-full font-medium", cfg.color, cfg.bg)}>
      {cfg.label}
    </span>
  );
}

function FilterBar<T extends string>({
  filters, active, onChange,
}: { filters: readonly T[]; active: T; onChange: (f: T) => void }) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {filters.map((f) => (
        <button
          key={f}
          onClick={() => onChange(f)}
          className={cn(
            "px-3 py-1.5 rounded-md text-xs font-medium capitalize transition-colors",
            active === f
              ? "bg-accent text-white"
              : "bg-elevated text-ink-muted hover:text-ink-primary"
          )}
        >
          {f}
        </button>
      ))}
    </div>
  );
}

// ── Email thread card ─────────────────────────────────────────

function EmailThreadCard({
  thread, ventureId, onWhitelistToggle,
}: {
  thread: EmailThread;
  ventureId: string;
  onWhitelistToggle: (email: string, add: boolean) => void;
}) {
  const statusCfg  = EMAIL_STATUS_CONFIG[thread.status] ?? EMAIL_STATUS_CONFIG.fetched;
  const StatusIcon = statusCfg.icon;

  return (
    <div className={cn(
      "card p-4 space-y-3 transition-all",
      thread.category === "urgent" && "border-danger/20"
    )}>
      <div className="flex items-start gap-3">
        <div className={cn(
          "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold",
          thread.is_whitelisted ? "bg-success/15 text-success" : "bg-elevated text-ink-muted"
        )}>
          {(thread.sender_name || thread.sender_email)[0].toUpperCase()}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-ink-primary truncate">
              {thread.sender_name || thread.sender_email}
            </span>
            {thread.is_whitelisted && (
              <span className="text-xs text-success bg-success/10 px-1.5 py-0.5 rounded-full flex items-center gap-1">
                <Shield className="w-3 h-3" /> Whitelisted
              </span>
            )}
            <CategoryBadge category={thread.category} />
          </div>
          <p className="text-xs text-ink-muted mono mt-0.5">{thread.sender_email}</p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <PriorityBar score={thread.priority_score} />
          <span className={cn(
            "text-xs px-2 py-0.5 rounded-full flex items-center gap-1",
            statusCfg.color, statusCfg.bg
          )}>
            <StatusIcon className="w-3 h-3" />
            {statusCfg.label}
          </span>
        </div>
      </div>

      <div>
        <p className="text-sm font-medium text-ink-primary">{thread.subject}</p>
        <p className="text-xs text-ink-muted mt-0.5 line-clamp-2">{thread.body_snippet}</p>
      </div>

      {thread.triage_notes && (
        <div className="bg-elevated rounded-md px-3 py-2">
          <p className="text-xs text-ink-muted">
            <span className="text-ink-secondary font-medium">Triage: </span>
            {thread.triage_notes}
          </p>
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-ink-muted mono">
          {formatDistanceToNow(new Date(thread.created_at), { addSuffix: true })}
        </span>
        <button
          onClick={() => onWhitelistToggle(thread.sender_email, !thread.is_whitelisted)}
          className="btn-ghost text-xs gap-1.5 text-ink-muted"
        >
          {thread.is_whitelisted
            ? <><ShieldOff className="w-3.5 h-3.5" /> Remove whitelist</>
            : <><Shield className="w-3.5 h-3.5" /> Add to whitelist</>
          }
        </button>
      </div>
    </div>
  );
}

// ── Social mention card ───────────────────────────────────────

function SocialMentionCard({
  mention, ventureId,
  onWhitelistToggle, onIgnore,
}: {
  mention: SocialMention;
  ventureId: string;
  onWhitelistToggle: (id: string, add: boolean) => void;
  onIgnore: (id: string) => void;
}) {
  const [showTriage, setShowTriage] = useState(false);
  const statusCfg  = SOCIAL_STATUS_CONFIG[mention.status] ?? SOCIAL_STATUS_CONFIG.fetched;
  const StatusIcon = statusCfg.icon;
  const tweetUrl   = mention.mention_id?.startsWith("mock")
    ? null
    : `https://x.com/i/web/status/${mention.mention_id}`;

  return (
    <div className={cn(
      "card p-4 space-y-3 transition-all",
      mention.category === "urgent" && "border-danger/20",
      mention.status === "ignored" && "opacity-50"
    )}>
      <div className="flex items-start gap-3">
        <div className={cn(
          "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold",
          mention.is_whitelisted ? "bg-success/15 text-success" : "bg-elevated text-ink-muted"
        )}>
          {mention.author_username[0].toUpperCase()}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-ink-primary">
              @{mention.author_username}
            </span>
            {mention.is_whitelisted && (
              <span className="text-xs text-success bg-success/10 px-1.5 py-0.5 rounded-full flex items-center gap-1">
                <Shield className="w-3 h-3" /> Whitelisted
              </span>
            )}
            <CategoryBadge category={mention.category} />
          </div>
          <p className="text-xs text-ink-muted mono mt-0.5">
            {mention.platform === "twitter" ? "X (Twitter)" : mention.platform}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <PriorityBar score={mention.priority_score} />
          <span className={cn(
            "text-xs px-2 py-0.5 rounded-full flex items-center gap-1",
            statusCfg.color, statusCfg.bg
          )}>
            <StatusIcon className="w-3 h-3" />
            {statusCfg.label}
          </span>
        </div>
      </div>

      <p className="text-sm text-ink-primary leading-relaxed">{mention.text}</p>

      {mention.triage_notes && (
        <div>
          <button
            onClick={() => setShowTriage(!showTriage)}
            className="flex items-center gap-1 text-xs text-ink-muted hover:text-ink-primary transition-colors"
          >
            {showTriage ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            Triage notes
          </button>
          {showTriage && (
            <div className="mt-2 bg-elevated rounded-md px-3 py-2">
              <p className="text-xs text-ink-muted">{mention.triage_notes}</p>
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between flex-wrap gap-2">
        <span className="text-xs text-ink-muted mono">
          {formatDistanceToNow(new Date(mention.created_at), { addSuffix: true })}
        </span>

        <div className="flex items-center gap-1 flex-wrap">
          {tweetUrl && (
            <a
              href={tweetUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost text-xs gap-1.5 text-ink-muted"
            >
              <ExternalLink className="w-3.5 h-3.5" /> View tweet
            </a>
          )}

          {mention.status !== "ignored" && (
            <button
              onClick={() => onIgnore(mention.id)}
              className="btn-ghost text-xs gap-1.5 text-ink-muted"
            >
              <EyeOff className="w-3.5 h-3.5" /> Ignore
            </button>
          )}

          <button
            onClick={() => onWhitelistToggle(mention.id, !mention.is_whitelisted)}
            className="btn-ghost text-xs gap-1.5 text-ink-muted"
          >
            {mention.is_whitelisted
              ? <><ShieldOff className="w-3.5 h-3.5" /> Unwhitelist</>
              : <><Shield className="w-3.5 h-3.5" /> Whitelist</>
            }
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────

export default function InboxPage() {
  const ventureId   = useVentureStore((s) => s.activeVentureId);
  const queryClient = useQueryClient();

  const [emailFilter,  setEmailFilter]  = useState<typeof EMAIL_FILTERS[number]>("all");
  const [socialFilter, setSocialFilter] = useState<typeof SOCIAL_FILTERS[number]>("all");

  // ── Queries ─────────────────────────────────────────────────

  const { data: emailData, isLoading: emailLoading } = useQuery({
    queryKey: ["inbox-email", ventureId, emailFilter],
    queryFn:  async () => {
      const { data } = await api.get(
        `/ventures/${ventureId}/inbox?status_filter=${emailFilter}&limit=100`
      );
      return data;
    },
    enabled:        !!ventureId,
    refetchInterval: 30_000,
  });

  const { data: socialData, isLoading: socialLoading } = useQuery({
    queryKey: ["inbox-social", ventureId, socialFilter],
    queryFn:  async () => {
      const { data } = await api.get(
        `/ventures/${ventureId}/inbox/social?status_filter=${socialFilter}&limit=100`
      );
      return data;
    },
    enabled:        !!ventureId,
    refetchInterval: 30_000,
  });

  // ── Mutations ────────────────────────────────────────────────

  const { mutate: triggerEmail, isPending: emailRunning } = useMutation({
    mutationFn: () => publishApi.runEmail(ventureId!),
    onSuccess:  () => {
      toast.success("Email cycle queued — check back in a moment.");
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["inbox-email", ventureId] }), 5000);
    },
    onError: () => toast.error("Failed to trigger email cycle."),
  });

  const { mutate: triggerSocial, isPending: socialRunning } = useMutation({
    mutationFn: () => publishApi.runSocial(ventureId!),
    onSuccess:  () => {
      toast.success("Social cycle queued — checking mentions...");
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["inbox-social", ventureId] }), 5000);
    },
    onError: () => toast.error("Failed to trigger social cycle."),
  });

  const { mutate: toggleEmailWhitelist } = useMutation({
    mutationFn: async ({ email, add }: { email: string; add: boolean }) => {
      if (add) {
        await api.post(`/ventures/${ventureId}/inbox/whitelist`, { email });
      } else {
        await api.delete(`/ventures/${ventureId}/inbox/whitelist`, { data: { email } });
      }
    },
    onSuccess: (_, { email, add }) => {
      toast.success(add ? `${email} whitelisted.` : `${email} removed from whitelist.`);
      queryClient.invalidateQueries({ queryKey: ["inbox-email", ventureId] });
    },
    onError: () => toast.error("Failed to update whitelist."),
  });

  const { mutate: toggleSocialWhitelist } = useMutation({
    mutationFn: async ({ id, add }: { id: string; add: boolean }) => {
      if (add) {
        await api.post(`/ventures/${ventureId}/inbox/social/${id}/whitelist`);
      } else {
        await api.delete(`/ventures/${ventureId}/inbox/social/${id}/whitelist`);
      }
    },
    onSuccess: (_, { add }) => {
      toast.success(add ? "Author whitelisted." : "Author removed from whitelist.");
      queryClient.invalidateQueries({ queryKey: ["inbox-social", ventureId] });
    },
    onError: () => toast.error("Failed to update whitelist."),
  });

  const { mutate: ignoreMention } = useMutation({
    mutationFn: (id: string) =>
      api.post(`/ventures/${ventureId}/inbox/social/${id}/ignore`),
    onSuccess: () => {
      toast.success("Mention ignored.");
      queryClient.invalidateQueries({ queryKey: ["inbox-social", ventureId] });
    },
    onError: () => toast.error("Failed to ignore mention."),
  });

  // ── Render ───────────────────────────────────────────────────

  const threads:  EmailThread[]   = emailData?.threads  ?? [];
  const mentions: SocialMention[] = socialData?.mentions ?? [];

  if (!ventureId) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center space-y-2">
        <Mail className="w-10 h-10 text-ink-muted" />
        <p className="text-ink-muted">Select a venture to view inbox.</p>
      </div>
    );
  }

  return (
    <div className="space-y-10 animate-fade-in">

      {/* ── Page header ─────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-ink-primary">Inbox</h1>
          <p className="text-sm text-ink-muted mt-0.5">
            Email and social mentions · fetch → triage → draft → send
          </p>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════
          EMAIL SECTION
      ══════════════════════════════════════════════════════ */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Mail className="w-5 h-5 text-accent" />
            <h2 className="text-lg font-semibold text-ink-primary">Email</h2>
            {threads.length > 0 && (
              <span className="text-xs bg-elevated text-ink-muted px-2 py-0.5 rounded-full">
                {threads.length}
              </span>
            )}
          </div>
          <button
            onClick={() => triggerEmail()}
            disabled={emailRunning}
            className="btn-secondary text-sm flex items-center gap-2"
          >
            <RefreshCw className={cn("w-4 h-4", emailRunning && "animate-spin")} />
            {emailRunning ? "Running..." : "Check inbox"}
          </button>
        </div>

        <FilterBar
          filters={EMAIL_FILTERS}
          active={emailFilter}
          onChange={setEmailFilter}
        />

        {emailLoading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-28 rounded-lg bg-elevated animate-pulse" />
            ))}
          </div>
        ) : threads.length === 0 ? (
          <div className="card p-10 text-center space-y-2">
            <Mail className="w-8 h-8 text-ink-muted mx-auto" />
            <p className="text-ink-primary font-medium">No email threads</p>
            <p className="text-sm text-ink-muted">
              {emailFilter === "all"
                ? "Click \"Check inbox\" to fetch emails from Gmail."
                : `No threads with status "${emailFilter}".`
              }
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {threads.map((thread) => (
              <EmailThreadCard
                key={thread.id}
                thread={thread}
                ventureId={ventureId}
                onWhitelistToggle={(email, add) => toggleEmailWhitelist({ email, add })}
              />
            ))}
          </div>
        )}
      </section>

      {/* ══════════════════════════════════════════════════════
          SOCIAL SECTION
      ══════════════════════════════════════════════════════ */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Twitter className="w-5 h-5 text-accent" />
            <h2 className="text-lg font-semibold text-ink-primary">Social Mentions</h2>
            {mentions.length > 0 && (
              <span className="text-xs bg-elevated text-ink-muted px-2 py-0.5 rounded-full">
                {mentions.length}
              </span>
            )}
          </div>
          <button
            onClick={() => triggerSocial()}
            disabled={socialRunning}
            className="btn-primary text-sm flex items-center gap-2"
          >
            <Zap className={cn("w-4 h-4", socialRunning && "animate-spin")} />
            {socialRunning ? "Checking..." : "Check social"}
          </button>
        </div>

        <FilterBar
          filters={SOCIAL_FILTERS}
          active={socialFilter}
          onChange={setSocialFilter}
        />

        {socialLoading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-24 rounded-lg bg-elevated animate-pulse" />
            ))}
          </div>
        ) : mentions.length === 0 ? (
          <div className="card p-10 text-center space-y-2">
            <Twitter className="w-8 h-8 text-ink-muted mx-auto" />
            <p className="text-ink-primary font-medium">No mentions</p>
            <p className="text-sm text-ink-muted">
              {socialFilter === "all"
                ? "Click \"Check social\" to fetch mentions from X."
                : `No mentions with status "${socialFilter}".`
              }
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {mentions.map((mention) => (
              <SocialMentionCard
                key={mention.id}
                mention={mention}
                ventureId={ventureId}
                onWhitelistToggle={(id, add) => toggleSocialWhitelist({ id, add })}
                onIgnore={(id) => ignoreMention(id)}
              />
            ))}
          </div>
        )}
      </section>

    </div>
  );
}