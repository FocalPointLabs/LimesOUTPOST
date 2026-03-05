"use client";

import { useState } from "react";
import { useVentureStore } from "@/store";
import { useQueue, usePatchQueueItem } from "@/lib/hooks";
import {
  CheckCircle2, XCircle, Filter, RefreshCw,
  ChevronDown, Loader2, Tag, Calendar, Trash2
} from "lucide-react";
import { formatDistanceToNow, format } from "date-fns";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";
import type { QueueItem, QueueStatus } from "@/types";

const STATUS_CONFIG: Record<QueueStatus, { label: string; color: string; bg: string; dot: string }> = {
  pending_review: { label: "Pending",    color: "text-warning",  bg: "bg-warning/10 border-warning/20",  dot: "bg-warning"  },
  approved:       { label: "Approved",   color: "text-success",  bg: "bg-success/10 border-success/20",  dot: "bg-success"  },
  rejected:       { label: "Rejected",   color: "text-danger",   bg: "bg-danger/10 border-danger/20",    dot: "bg-danger"   },
  publishing:     { label: "Publishing", color: "text-accent",   bg: "bg-accent/10 border-accent/20",    dot: "bg-accent animate-pulse-slow" },
  published:      { label: "Published",  color: "text-success",  bg: "bg-success/10 border-success/20",  dot: "bg-success"  },
  failed:         { label: "Failed",     color: "text-danger",   bg: "bg-danger/10 border-danger/20",    dot: "bg-danger"   },
};

const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube",
  twitter: "Twitter / X",
  email:   "Email",
  blog:    "Blog",
};

const COMPLETED_STATUSES = new Set(["approved", "rejected", "published", "failed"]);

function QueueCard({
  item,
  ventureId,
  optimisticStatus,
  onAction,
}: {
  item: QueueItem;
  ventureId: string;
  optimisticStatus?: QueueStatus;
  onAction: (id: string, status: QueueStatus) => void;
}) {
  const { mutate: patch, isPending } = usePatchQueueItem(ventureId);
  const [expanded, setExpanded] = useState(false);

  const displayStatus = optimisticStatus ?? item.status;
  const cfg           = STATUS_CONFIG[displayStatus];
  const isActioned    = !!optimisticStatus && optimisticStatus !== "pending_review";

  function approve() {
    onAction(item.id, "approved");
    patch({ itemId: item.id, body: { action: "approve" } }, {
      onError: () => {
        onAction(item.id, "pending_review"); // revert on error
        toast.error("Failed to approve");
      },
    });
  }

  function reject() {
    onAction(item.id, "rejected");
    patch({ itemId: item.id, body: { action: "reject", reason: "Rejected by operator" } }, {
      onError: () => {
        onAction(item.id, "pending_review"); // revert on error
        toast.error("Failed to reject");
      },
    });
  }

  return (
    <div className={cn(
      "card border transition-all duration-300",
      displayStatus === "pending_review" && "border-warning/20 hover:border-warning/40",
      displayStatus === "approved"        && "border-success/30 bg-success/5 opacity-80",
      displayStatus === "rejected"        && "border-danger/30 bg-danger/5 opacity-60",
    )}>
      {/* Header row */}
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 pt-0.5">
            <span className={cn("status-dot", cfg.dot)} />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <h3 className={cn(
                "text-sm font-semibold leading-snug transition-colors",
                isActioned ? "text-ink-muted line-through decoration-1" : "text-ink-primary"
              )}>
                {item.title ?? "Untitled"}
              </h3>
              <span className={cn(
                "text-xs px-2 py-0.5 rounded-full border font-medium flex-shrink-0",
                cfg.color, cfg.bg
              )}>
                {cfg.label}
              </span>
            </div>

            <div className="flex items-center gap-3 mt-1.5 flex-wrap">
              <span className="text-xs text-ink-muted font-mono bg-elevated px-2 py-0.5 rounded">
                {PLATFORM_LABELS[item.platform] ?? item.platform}
              </span>
              <span className="text-xs text-ink-muted">
                {formatDistanceToNow(new Date(item.created_at), { addSuffix: true })}
              </span>
              {item.scheduled_for && (
                <span className="text-xs text-accent flex items-center gap-1">
                  <Calendar className="w-3 h-3" />
                  {format(new Date(item.scheduled_for), "MMM d, h:mm a")}
                </span>
              )}
            </div>

            {/* Tags — hide email metadata tags, show real tags */}
            {item.tags && item.tags.length > 0 && item.platform !== "email" && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {item.tags.map((tag) => (
                  <span key={tag} className="text-xs text-ink-muted bg-elevated px-1.5 py-0.5 rounded flex items-center gap-1">
                    <Tag className="w-2.5 h-2.5" />
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Expand toggle */}
        {item.description && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-ink-muted hover:text-ink-secondary mt-2 ml-5 transition-colors"
          >
            <ChevronDown className={cn("w-3 h-3 transition-transform", expanded && "rotate-180")} />
            {expanded ? "Hide" : "Show"} {item.platform === "email" ? "draft" : "description"}
          </button>
        )}
      </div>

      {/* Expanded description */}
      {expanded && item.description && (
        <div className="px-4 pb-3 ml-5">
          <p className="text-sm text-ink-secondary leading-relaxed border-l-2 border-border pl-3 whitespace-pre-wrap">
            {item.description}
          </p>
        </div>
      )}

      {/* Action bar — only for pending items */}
      {displayStatus === "pending_review" && (
        <div className="px-4 pb-4 flex items-center gap-2 ml-5">
          <button
            onClick={approve}
            disabled={isPending}
            className="btn-primary text-xs py-1.5 px-3"
          >
            {isPending
              ? <Loader2 className="w-3 h-3 animate-spin" />
              : <CheckCircle2 className="w-3 h-3" />
            }
            Approve
          </button>
          <button
            onClick={reject}
            disabled={isPending}
            className="btn-secondary text-xs py-1.5 px-3 hover:border-danger/40 hover:text-danger"
          >
            <XCircle className="w-3 h-3" />
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

const STATUS_FILTERS = [
  { value: "pending_review", label: "Pending"   },
  { value: "approved",       label: "Approved"  },
  { value: "published",      label: "Published" },
  { value: "rejected",       label: "Rejected"  },
  { value: "all",            label: "All"       },
];

export default function QueuePage() {
  const activeVentureId = useVentureStore((s) => s.activeVentureId);
  const [statusFilter, setStatusFilter] = useState("pending_review");
  const [platform,     setPlatform]     = useState<string | undefined>();

  // Optimistic status overrides — keyed by item id
  const [optimisticMap, setOptimisticMap] = useState<Record<string, QueueStatus>>({});

  const { data: queue, isLoading, refetch, isFetching } = useQueue(
    activeVentureId,
    { status_filter: statusFilter, platform }
  );

  function handleAction(id: string, status: QueueStatus) {
    setOptimisticMap((prev) => ({ ...prev, [id]: status }));
  }

  function clearCompleted() {
    // Remove all items from optimistic map that are in a completed state
    setOptimisticMap((prev) => {
      const next = { ...prev };
      for (const [id, status] of Object.entries(next)) {
        if (COMPLETED_STATUSES.has(status)) delete next[id];
      }
      return next;
    });
    // Also refetch to get fresh server state
    refetch();
  }

  // Items to display — hide ones that have been optimistically actioned
  const displayQueue = queue?.filter((item) => {
    const optimistic = optimisticMap[item.id];
    // If we've actioned this item optimistically, hide it from pending view
    if (statusFilter === "pending_review" && optimistic && COMPLETED_STATUSES.has(optimistic)) {
      return false;
    }
    return true;
  });

  const actionedCount = Object.values(optimisticMap).filter(
    (s) => COMPLETED_STATUSES.has(s)
  ).length;

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-ink-primary">Review Queue</h1>
          <p className="text-sm text-ink-muted mt-0.5">
            {displayQueue
              ? `${displayQueue.length} item${displayQueue.length !== 1 ? "s" : ""}`
              : "—"}
            {statusFilter !== "all" && ` · ${STATUS_FILTERS.find(f => f.value === statusFilter)?.label}`}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Clear completed — shows when items have been actioned */}
          {actionedCount > 0 && statusFilter === "pending_review" && (
            <button
              onClick={clearCompleted}
              className="btn-ghost text-xs gap-1.5 text-ink-muted hover:text-danger"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Clear {actionedCount} actioned
            </button>
          )}

          {/* Refresh */}
          <button
            onClick={() => { setOptimisticMap({}); refetch(); }}
            disabled={isFetching}
            className="btn-ghost"
            title="Refresh queue"
          >
            <RefreshCw className={cn("w-4 h-4", isFetching && "animate-spin")} />
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <Filter className="w-3.5 h-3.5 text-ink-muted" />
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => { setStatusFilter(f.value); setOptimisticMap({}); }}
            className={cn(
              "text-xs px-3 py-1.5 rounded-full border transition-all duration-100",
              statusFilter === f.value
                ? "bg-accent/10 border-accent/40 text-accent"
                : "bg-elevated border-border text-ink-muted hover:text-ink-secondary hover:border-border/80"
            )}
          >
            {f.label}
          </button>
        ))}
        <div className="w-px h-4 bg-border mx-1" />
        {["youtube", "twitter", "email", "blog"].map((p) => (
          <button
            key={p}
            onClick={() => setPlatform(platform === p ? undefined : p)}
            className={cn(
              "text-xs px-3 py-1.5 rounded-full border transition-all duration-100 font-mono",
              platform === p
                ? "bg-accent/10 border-accent/40 text-accent"
                : "bg-elevated border-border text-ink-muted hover:text-ink-secondary"
            )}
          >
            {p}
          </button>
        ))}
      </div>

      {/* Queue list */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 rounded-lg bg-elevated animate-pulse" />
          ))}
        </div>
      ) : !activeVentureId ? (
        <div className="card p-8 text-center text-ink-muted text-sm">
          Select a venture to view the queue.
        </div>
      ) : displayQueue?.length === 0 ? (
        <div className="card p-12 text-center space-y-2">
          <CheckCircle2 className="w-8 h-8 text-success mx-auto opacity-50" />
          <p className="text-ink-primary font-medium">All clear</p>
          <p className="text-sm text-ink-muted">
            {statusFilter === "pending_review"
              ? "Nothing waiting for review right now."
              : "No items match this filter."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {displayQueue?.map((item) => (
            <QueueCard
              key={item.id}
              item={item}
              ventureId={activeVentureId!}
              optimisticStatus={optimisticMap[item.id]}
              onAction={handleAction}
            />
          ))}
        </div>
      )}
    </div>
  );
}