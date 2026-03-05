"use client";

import { useVentureStore } from "@/store";
import { useAnalytics } from "@/lib/hooks";
import { TrendingUp, Eye, ThumbsUp, MousePointer, Clock, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import { format } from "date-fns";

function MetricCard({ label, value, icon: Icon, sub }: {
  label: string; value: string; icon: React.ElementType; sub?: string;
}) {
  return (
    <div className="card p-5 flex items-start gap-3">
      <div className="w-9 h-9 rounded-md bg-accent/10 flex items-center justify-center flex-shrink-0">
        <Icon className="w-4 h-4 text-accent" />
      </div>
      <div>
        <p className="text-2xl font-bold text-ink-primary font-mono">{value}</p>
        <p className="text-xs text-ink-secondary mt-0.5">{label}</p>
        {sub && <p className="text-xs text-ink-muted mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

function fmt(n: number | null | undefined, type: "number" | "percent" | "duration" = "number") {
  if (n == null) return "—";
  if (type === "percent")  return `${(n * 100).toFixed(1)}%`;
  if (type === "duration") return `${Math.round(n)}s`;
  return Intl.NumberFormat("en", { notation: "compact" }).format(n);
}

export default function AnalyticsPage() {
  const activeVentureId = useVentureStore((s) => s.activeVentureId);
  const { data, isLoading } = useAnalytics(activeVentureId);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-ink-primary">Analytics</h1>
          <p className="text-sm text-ink-muted mt-0.5">
            YouTube · last 30 days
            {data?.as_of && (
              <span className="ml-2 text-ink-muted/60">
                · updated {format(new Date(data.as_of), "MMM d, h:mm a")}
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Metrics grid */}
      {isLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 rounded-lg bg-elevated animate-pulse" />
          ))}
        </div>
      ) : !activeVentureId ? (
        <div className="card p-8 text-center text-ink-muted text-sm">
          Select a venture to view analytics.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <MetricCard label="Total views"  value={fmt(data?.total_views)} icon={Eye}           sub="YouTube" />
            <MetricCard label="Total likes"  value={fmt(data?.total_likes)} icon={ThumbsUp}      sub="YouTube" />
            <MetricCard label="Avg. CTR"     value={fmt(data?.avg_ctr, "percent")} icon={MousePointer} sub="YouTube" />
            <MetricCard label="Top asset"    value={data?.top_asset_id ? "View →" : "—"} icon={TrendingUp} />
          </div>

          {!data?.total_views && (
            <div className="card p-8 text-center space-y-2">
              <BarChart3 className="w-8 h-8 text-ink-muted mx-auto opacity-40" />
              <p className="text-ink-primary font-medium">No analytics data yet</p>
              <p className="text-sm text-ink-muted">
                Analytics populate once the Beat scheduler runs the daily pull task,
                or you can trigger it manually from the pipeline page.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
