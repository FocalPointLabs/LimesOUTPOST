"use client";

import { useState } from "react";
import { useVentureStore } from "@/store";
import { useQueue, usePatchQueueItem, useTriggerPublish } from "@/lib/hooks";
import {
  CheckCircle2, XCircle, Filter, RefreshCw,
  ChevronDown, Loader2, Tag, Calendar, Trash2, Send
} from "lucide-react";
import { formatDistanceToNow, format } from "date-fns";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";
import type { QueueItem, QueueStatus } from "@/types";

/**
 * Constants defined locally
 */
const PLATFORM_LABELS: Record<string, string> = {
  youtube: "YouTube",
  twitter: "Twitter",
  email: "Email",
};

const STATUS_CONFIG: Record<QueueStatus, { label: string; color: string; bg: string; dot: string }> = {
  pending_review: { label: "Pending",    color: "text-warning",  bg: "bg-warning/10 border-warning/20",  dot: "bg-warning"  },
  approved:       { label: "Approved",   color: "text-success",  bg: "bg-success/10 border-success/20",  dot: "bg-success"  },
  rejected:       { label: "Rejected",   color: "text-danger",   bg: "bg-danger/10 border-danger/20",    dot: "bg-danger"   },
  publishing:     { label: "Publishing", color: "text-accent",   bg: "bg-accent/10 border-accent/20",    dot: "bg-accent animate-pulse-slow" },
  published:      { label: "Published",  color: "text-success",  bg: "bg-success/10 border-success/20",  dot: "bg-success"  },
  failed:         { label: "Failed",     color: "text-danger",   bg: "bg-danger/10 border-danger/20",    dot: "bg-danger"   },
};

const COMPLETED_STATUSES = new Set(["approved", "rejected", "published", "failed"]);

function QueueCard({
  item,
  ventureId,
  optimisticStatus,
  onAction,
  onPublishNow,
}: {
  item: QueueItem;
  ventureId: string;
  optimisticStatus?: QueueStatus;
  onAction: (id: string, status: QueueStatus) => void;
  onPublishNow: (platform: string) => void;
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
        onAction(item.id, "pending_review");
        toast.error("Failed to approve");
      },
    });
  }

  function reject() {
    onAction(item.id, "rejected");
    patch({ itemId: item.id, body: { action: "reject", reason: "Rejected by operator" } }, {
      onError: () => {
        onAction(item.id, "pending_review");
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
          </div>
        </div>

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

      {expanded && item.description && (
        <div className="px-4 pb-3 ml-5">
          <p className="text-sm text-ink-secondary leading-relaxed border-l-2 border-border pl-3 whitespace-pre-wrap">
            {item.description}
          </p>
        </div>
      )}

      {displayStatus === "pending_review" && (
        <div className="px-4 pb-4 flex items-center gap-2 ml-5">
          <button onClick={approve} disabled={isPending} className="btn-primary text-xs py-1.5 px-3">
            {isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
            Approve
          </button>
          <button onClick={reject} disabled={isPending} className="btn-secondary text-xs py-1.5 px-3 hover:border-danger/40 hover:text-danger">
            <XCircle className="w-3 h-3" />
            Reject
          </button>
        </div>
      )}

      {displayStatus === "approved" && (
        <div className="px-4 pb-4 flex items-center gap-3 ml-5">
          <button
            onClick={() => onPublishNow(item.platform)}
            className="text-[10px] font-medium uppercase tracking-wider text-accent hover:text-accent-hover flex items-center gap-1.5 border border-accent/20 px-2 py-1 rounded bg-accent/5"
          >
            <Send className="w-3 h-3" />
            Push to {PLATFORM_LABELS[item.platform]} Now
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
  const [optimisticMap, setOptimisticMap] = useState<Record<string, QueueStatus>>({});
  
  const [confirmPlatform, setConfirmPlatform] = useState<string | null>(null);
  const [isConfirmingClear, setIsConfirmingClear] = useState(false);

  const { data: queue, isLoading, refetch, isFetching } = useQueue(
    activeVentureId,
    { status_filter: statusFilter, platform }
  );

  const { mutate: triggerPublish, isPending: isPublishing } = useTriggerPublish(activeVentureId);

  const handlePublish = (p: string) => {
    triggerPublish(p, {
      onSuccess: () => {
        toast.success(`Publishing started...`);
        setConfirmPlatform(null);
      },
      onError: () => {
        toast.error("Failed to trigger publish");
        setConfirmPlatform(null);
      }
    });
  };

  function handleAction(id: string, status: QueueStatus) {
    setOptimisticMap((prev) => ({ ...prev, [id]: status }));
  }

  function clearCompleted() {
    setOptimisticMap((prev) => {
      const next = { ...prev };
      for (const [id, status] of Object.entries(next)) {
        if (COMPLETED_STATUSES.has(status)) delete next[id];
      }
      return next;
    });
    setIsConfirmingClear(false);
    refetch();
  }

  const actionedCount = Object.values(optimisticMap).filter(
    (s) => COMPLETED_STATUSES.has(s)
  ).length;

  const displayQueue = queue?.filter((item) => {
    const optimistic = optimisticMap[item.id];
    if (statusFilter === "pending_review" && optimistic && COMPLETED_STATUSES.has(optimistic)) {
      return false;
    }
    return true;
  });

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-ink-primary">Review Queue</h1>
          <p className="text-sm text-ink-muted mt-0.5">
            {displayQueue ? `${displayQueue.length} item${displayQueue.length !== 1 ? "s" : ""}` : "—"}
            {statusFilter !== "all" && ` · ${STATUS_FILTERS.find(f => f.value === statusFilter)?.label}`}
          </p>
        </div>

        <div className="flex items-center gap-4">
          {/* Clear Actioned Button - Rendered separately to prevent layout shifts */}
          {actionedCount > 0 && statusFilter === "pending_review" && (
            <div className="animate-in slide-in-from-right-2">
              {isConfirmingClear ? (
                <div className="flex items-center gap-1 bg-danger/5 border border-danger/20 rounded-md p-0.5">
                  <button onClick={clearCompleted} className="px-2 py-1 text-[10px] font-bold text-danger hover:bg-danger/10 rounded">Confirm Clear</button>
                  <button onClick={() => setIsConfirmingClear(false)} className="px-2 py-1 text-[10px] text-ink-muted hover:text-ink-primary">Cancel</button>
                </div>
              ) : (
                <button onClick={() => setIsConfirmingClear(true)} className="btn-ghost text-xs gap-1.5 text-ink-muted hover:text-danger">
                  <Trash2 className="w-3.5 h-3.5" /> Clear {actionedCount}
                </button>
              )}
            </div>
          )}

          <div className="flex items-center gap-2">
            {/* Publish Dropdown - Always anchored right */}
            <div className="relative group">
              <button
                disabled={isPublishing || !activeVentureId}
                className="btn-primary text-xs py-1.5 px-3 flex items-center gap-2"
              >
                {isPublishing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                Publish Now
                <ChevronDown className="w-3 h-3" />
              </button>
              
              <div className="absolute right-0 mt-2 w-48 bg-elevated border border-border rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 p-1">
                {confirmPlatform ? (
                  <div className="p-2 space-y-2">
                    <p className="text-[10px] text-ink-secondary font-medium">
                      Confirm {confirmPlatform === 'all' ? 'ALL' : PLATFORM_LABELS[confirmPlatform]}?
                    </p>
                    <div className="flex gap-1">
                      <button onClick={() => handlePublish(confirmPlatform)} className="flex-1 bg-success/10 text-success text-[10px] py-1 rounded border border-success/20">Confirm</button>
                      <button onClick={() => setConfirmPlatform(null)} className="flex-1 bg-elevated text-ink-muted text-[10px] py-1 rounded border border-border">Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col">
                    <button onClick={() => setConfirmPlatform('all')} className="text-left px-3 py-2 text-xs hover:bg-accent/10 rounded">All Platforms</button>
                    <div className="h-px bg-border my-1" />
                    {Object.entries(PLATFORM_LABELS).map(([id, label]) => (
                      <button key={id} onClick={() => setConfirmPlatform(id)} className="text-left px-3 py-2 text-xs hover:bg-accent/10 rounded">{label}</button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <button onClick={() => { setOptimisticMap({}); refetch(); }} disabled={isFetching} className="btn-ghost" title="Refresh queue">
              <RefreshCw className={cn("w-4 h-4", isFetching && "animate-spin")} />
            </button>
          </div>
        </div>
      </div>

      {/* Filters Bar */}
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
        {Object.keys(PLATFORM_LABELS).map((p) => (
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

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => <div key={i} className="h-24 rounded-lg bg-elevated animate-pulse" />)}
        </div>
      ) : displayQueue?.length === 0 ? (
        <div className="card p-12 text-center space-y-2">
          <CheckCircle2 className="w-8 h-8 text-success mx-auto opacity-50" />
          <p className="text-ink-primary font-medium">All clear</p>
          <p className="text-sm text-ink-muted">No items match this filter.</p>
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
              onPublishNow={(p) => setConfirmPlatform(p)}
            />
          ))}
        </div>
      )}
    </div>
  );
}