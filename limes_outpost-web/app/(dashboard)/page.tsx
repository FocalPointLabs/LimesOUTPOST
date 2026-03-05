"use client";

import { useVentureStore } from "@/store";
import { useQueue, useAnalytics, useVenture } from "@/lib/hooks";
import { ListChecks, GitBranch, TrendingUp, Clock, CheckCircle2, Zap, ArrowRight } from "lucide-react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import type { QueueItem } from "@/types";
import { PulseCard } from "@/components/dashboard/PulseCard";

const STATUS_CONFIG = {
  pending_review: { label: "Pending",    color: "text-warning",  bg: "bg-warning/10",  dot: "bg-warning"  },
  approved:       { label: "Approved",   color: "text-success",  bg: "bg-success/10",  dot: "bg-success"  },
  rejected:       { label: "Rejected",   color: "text-danger",   bg: "bg-danger/10",   dot: "bg-danger"   },
  publishing:     { label: "Publishing", color: "text-accent",   bg: "bg-accent/10",   dot: "bg-accent animate-pulse-slow" },
  published:      { label: "Published",  color: "text-success",  bg: "bg-success/10",  dot: "bg-success"  },
  failed:         { label: "Failed",     color: "text-danger",   bg: "bg-danger/10",   dot: "bg-danger"   },
};

function StatCard({ label, value, sub, icon: Icon, accent = false }: {
  label: string; value: string | number; sub?: string;
  icon: React.ElementType; accent?: boolean;
}) {
  return (
    <div className={cn(
      "card p-4 flex items-start gap-3",
      // border-accent/30 is enough to signal attention — no phantom shadow token needed
      accent && "border-accent/30"
    )}>
      <div className={cn(
        "w-9 h-9 rounded-md flex items-center justify-center flex-shrink-0",
        accent ? "bg-accent/15" : "bg-elevated"
      )}>
        <Icon className={cn("w-4 h-4", accent ? "text-accent" : "text-ink-secondary")} />
      </div>
      <div>
        <div className="text-xl font-bold text-ink-primary font-mono">{value}</div>
        <div className="text-xs text-ink-secondary">{label}</div>
        {sub && <div className="text-xs text-ink-muted mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

function QueueRow({ item }: { item: QueueItem }) {
  const cfg = STATUS_CONFIG[item.status] ?? STATUS_CONFIG.pending_review;
  return (
    <div className="flex items-center gap-3 py-2.5 px-3 rounded-md hover:bg-elevated/50 transition-colors group">
      <span className={cn("status-dot flex-shrink-0", cfg.dot)} />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-ink-primary truncate">
          {item.title ?? "Untitled"}
        </p>
        <p className="text-xs text-ink-muted font-mono">
          {item.platform} · {formatDistanceToNow(new Date(item.created_at), { addSuffix: true })}
        </p>
      </div>
      {/* rounded → radius-xs/sm — consistent with tag language, not pill-shaped */}
      <span className={cn("tag flex-shrink-0", cfg.color, cfg.bg)}>
        {cfg.label}
      </span>
    </div>
  );
}

export default function DashboardPage() {
  const activeVentureId = useVentureStore((s) => s.activeVentureId);
  const { data: venture } = useVenture(activeVentureId);
  const { data: queue,   isLoading: queueLoading }     = useQueue(activeVentureId, { status_filter: "all" });
  const { data: analytics, isLoading: analyticsLoading } = useAnalytics(activeVentureId);

  const pending   = queue?.filter((i) => i.status === "pending_review").length ?? 0;
  const approved  = queue?.filter((i) => i.status === "approved").length ?? 0;
  const published = queue?.filter((i) => i.status === "published").length ?? 0;
  const recent    = queue?.slice(0, 6) ?? [];

  if (!activeVentureId) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center space-y-4">
        <div className="w-12 h-12 rounded-xl bg-elevated flex items-center justify-center">
          <Zap className="w-6 h-6 text-ink-muted" />
        </div>
        <div>
          <p className="text-ink-primary font-semibold">No venture selected</p>
          <p className="text-ink-muted text-sm mt-1">Create or select a venture to get started.</p>
        </div>
        <Link href="/ventures/new" className="btn-primary">
          Create venture <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-ink-primary">
            {venture?.name ?? "Dashboard"}
          </h1>
          <p className="text-sm text-ink-muted font-mono mt-0.5">
            {activeVentureId}
            {venture && (
              // rounded → radius-xs, not pill — matches new badge language
              <span className={cn(
                "ml-2 text-xs px-1.5 py-0.5 rounded capitalize",
                venture.status === "active" ? "text-success bg-success/10" : "text-neutral bg-neutral/10"
              )}>
                {venture.status}
              </span>
            )}
          </p>
        </div>
        <Link href="/pipeline" className="btn-primary text-sm">
          <GitBranch className="w-4 h-4" />
          Run pipeline
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Pending review"
          value={queueLoading ? "—" : pending}
          icon={Clock}
          accent={pending > 0}
        />
        <StatCard
          label="Approved"
          value={queueLoading ? "—" : approved}
          icon={CheckCircle2}
        />
        <StatCard
          label="Published"
          value={queueLoading ? "—" : published}
          icon={Zap}
        />
        <StatCard
          label="Total views"
          value={analyticsLoading ? "—" : analytics?.total_views != null
            ? Intl.NumberFormat("en", { notation: "compact" }).format(analytics.total_views)
            : "—"
          }
          sub="YouTube · last 30d"
          icon={TrendingUp}
        />
      </div>

      <PulseCard ventureId={activeVentureId} />

      {/* Recent queue */}
      <div className="card p-4 space-y-1">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <ListChecks className="w-4 h-4 text-ink-muted" />
            <h2 className="text-sm font-semibold text-ink-primary">Recent queue</h2>
          </div>
          {/* accent-dim is the correct hover target — accent-glow is a CSS rgba shadow value */}
          <Link href="/queue" className="text-xs text-accent hover:text-accent-dim transition-colors flex items-center gap-1">
            View all <ArrowRight className="w-3 h-3" />
          </Link>
        </div>

        {queueLoading ? (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-10 rounded-md bg-elevated animate-pulse" />
            ))}
          </div>
        ) : recent.length === 0 ? (
          <div className="py-6 text-center text-sm text-ink-muted">
            Queue is empty — run the pipeline to generate content.
          </div>
        ) : (
          <div>
            {recent.map((item) => (
              <QueueRow key={item.id} item={item} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
