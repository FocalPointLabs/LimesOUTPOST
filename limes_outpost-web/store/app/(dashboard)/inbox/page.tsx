"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, publishApi } from "@/lib/api";
import { useVentureStore } from "@/store";
import {
  Mail, RefreshCw, Shield, ShieldOff, Inbox,
  AlertCircle, Clock, CheckCircle2, XCircle, Filter, Zap
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import toast from "react-hot-toast";

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
  updated_at: string;
}

const STATUS_CONFIG = {
  fetched:  { label: "Fetched",  icon: Inbox,        color: "text-ink-muted",    bg: "bg-elevated"       },
  triaged:  { label: "Triaged",  icon: Clock,         color: "text-warning",      bg: "bg-warning/10"     },
  drafted:  { label: "Drafted",  icon: Mail,          color: "text-accent",       bg: "bg-accent/10"      },
  sent:     { label: "Sent",     icon: CheckCircle2,  color: "text-success",      bg: "bg-success/10"     },
  ignored:  { label: "Ignored",  icon: XCircle,       color: "text-ink-muted",    bg: "bg-elevated"       },
};

const CATEGORY_CONFIG = {
  urgent: { label: "Urgent", color: "text-danger",   bg: "bg-danger/10"   },
  normal: { label: "Normal", color: "text-accent",   bg: "bg-accent/10"   },
  low:    { label: "Low",    color: "text-ink-muted", bg: "bg-elevated"   },
  ignore: { label: "Ignore", color: "text-ink-muted", bg: "bg-elevated"   },
};

const STATUS_FILTERS = ["all", "fetched", "triaged", "drafted", "sent", "ignored"] as const;

function PriorityBar({ score }: { score: number | null }) {
  if (!score) return null;
  const pct = (score / 10) * 100;
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

function ThreadCard({
  thread,
  ventureId,
  onWhitelistToggle,
}: {
  thread: EmailThread;
  ventureId: string;
  onWhitelistToggle: (email: string, add: boolean) => void;
}) {
  const statusCfg   = STATUS_CONFIG[thread.status] ?? STATUS_CONFIG.fetched;
  const categoryCfg = thread.category ? CATEGORY_CONFIG[thread.category] : null;
  const StatusIcon  = statusCfg.icon;

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
            {categoryCfg && (
              <span className={cn(
                "text-xs px-1.5 py-0.5 rounded-full font-medium",
                categoryCfg.color, categoryCfg.bg
              )}>
                {categoryCfg.label}
              </span>
            )}
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
            ? <><ShieldOff className="w-3.5 h-3.5" /> Remove from whitelist</>
            : <><Shield className="w-3.5 h-3.5" /> Add to whitelist</>
          }
        </button>
      </div>
    </div>
  );
}

export default function InboxPage() {
  const ventureId  = useVentureStore((s) => s.activeVentureId);
  const [filter, setFilter] = useState<typeof STATUS_FILTERS[number]>("all");
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["inbox", ventureId, filter],
    queryFn: async () => {
      const { data } = await api.get(
        `/ventures/${ventureId}/inbox?status_filter=${filter}&limit=100`
      );
      return data;
    },
    enabled: !!ventureId,
    refetchInterval: 30_000,
  });

  const { mutate: triggerCycle, isPending: isRunning } = useMutation({
    mutationFn: async () => {
      return publishApi.runEmail(ventureId!);
    },
    onSuccess: () => {
      toast.success("Email cycle queued — check back in a moment.");
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["inbox", ventureId] });
      }, 5000);
    },
    onError: () => toast.error("Failed to trigger email cycle."),
  });

  const { mutate: triggerSocial, isPending: isSocialRunning } = useMutation({
    mutationFn: async () => {
      return publishApi.runSocial(ventureId!);
    },
    onSuccess: () => {
      toast.success("Social sniper active — scouting mentions!");
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["inbox", ventureId] });
      }, 5000);
    },
    onError: () => toast.error("Failed to trigger social cycle."),
  });

  const { mutate: toggleWhitelist } = useMutation({
    mutationFn: async ({ email, add }: { email: string; add: boolean }) => {
      if (add) {
        await api.post(`/ventures/${ventureId}/inbox/whitelist`, { email });
      } else {
        await api.delete(`/ventures/${ventureId}/inbox/whitelist`, { data: { email } });
      }
    },
    onSuccess: (_, { email, add }) => {
      toast.success(add ? `${email} whitelisted.` : `${email} removed from whitelist.`);
      queryClient.invalidateQueries({ queryKey: ["inbox", ventureId] });
    },
    onError: () => toast.error("Failed to update whitelist."),
  });

  const threads: EmailThread[] = data?.threads ?? [];

  if (!ventureId) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center space-y-2">
        <Mail className="w-10 h-10 text-ink-muted" />
        <p className="text-ink-muted">Select a venture to view inbox.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-ink-primary">Inbox</h1>
          <p className="text-sm text-ink-muted mt-0.5">
            Omni-channel engagement · fetch → triage → draft → send
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => triggerCycle()}
            disabled={isRunning}
            className="btn-secondary text-sm flex items-center gap-2"
          >
            <RefreshCw className={cn("w-4 h-4", isRunning && "animate-spin")} />
            {isRunning ? "Running..." : "Check inbox"}
          </button>
          <button
            onClick={() => triggerSocial()}
            disabled={isSocialRunning}
            className="btn-primary text-sm flex items-center gap-2"
          >
            <Zap className={cn("w-4 h-4", isSocialRunning && "animate-spin")} />
            {isSocialRunning ? "Sniping..." : "Check social"}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-1 flex-wrap">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "px-3 py-1.5 rounded-md text-xs font-medium capitalize transition-colors",
              filter === f
                ? "bg-accent text-white"
                : "bg-elevated text-ink-muted hover:text-ink-primary"
            )}
          >
            {f}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-32 rounded-lg bg-elevated animate-pulse" />
          ))}
        </div>
      ) : threads.length === 0 ? (
        <div className="card p-12 text-center space-y-3">
          <Inbox className="w-10 h-10 text-ink-muted mx-auto" />
          <p className="text-ink-primary font-medium">No threads found</p>
          <p className="text-sm text-ink-muted">
            {filter === "all"
              ? "Click \"Check inbox\" to fetch emails from Gmail."
              : `No threads with status "${filter}".`
            }
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {threads.map((thread) => (
            <ThreadCard
              key={thread.id}
              thread={thread}
              ventureId={ventureId}
              onWhitelistToggle={(email, add) => toggleWhitelist({ email, add })}
            />
          ))}
        </div>
      )}
    </div>
  );
}