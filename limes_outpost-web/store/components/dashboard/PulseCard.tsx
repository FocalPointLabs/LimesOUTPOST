"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Zap, RefreshCw, ChevronDown, ChevronUp, Terminal } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";

interface PulseReport {
  id: string;
  venture_id: string;
  stats: {
    recent_renders: number;
    failed_contracts: number;
    total_tracked_items: number;
  };
  briefing: string;
  created_at: string;
}

async function fetchLatestPulse(ventureId: string): Promise<{ report: PulseReport | null }> {
  const { data } = await api.get(`/ventures/${ventureId}/pulse/latest`);
  return data;
}

async function triggerPulse(ventureId: string) {
  const { data } = await api.post(`/ventures/${ventureId}/pulse/run`);
  return data;
}

export function PulseCard({ ventureId }: { ventureId: string }) {
  const [expanded, setExpanded] = useState(false);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["pulse", ventureId],
    queryFn: () => fetchLatestPulse(ventureId),
    enabled: !!ventureId,
    refetchInterval: 60_000,
  });

  const { mutate: runPulse, isPending } = useMutation({
    mutationFn: () => triggerPulse(ventureId),
    onSuccess: () => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["pulse", ventureId] });
      }, 4000);
    },
  });

  const report = data?.report;

  return (
    <div className={cn(
      "card p-4 space-y-3 transition-all duration-200",
      report && "border-accent/20"
    )}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-md bg-accent/15 flex items-center justify-center">
            <Zap className="w-3.5 h-3.5 text-accent" fill="currentColor" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-ink-primary">Daily Pulse</h2>
            {report && (
              <p className="text-xs text-ink-muted mono">
                {formatDistanceToNow(new Date(report.created_at), { addSuffix: true })}
              </p>
            )}
          </div>
        </div>

        <button
          onClick={() => runPulse()}
          disabled={isPending || isLoading}
          className="btn-ghost text-xs gap-1.5 text-ink-muted"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", isPending && "animate-spin")} />
          {isPending ? "Running..." : "Run now"}
        </button>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-4 rounded bg-elevated animate-pulse" style={{ width: `${70 + i * 10}%` }} />
          ))}
        </div>
      )}

      {/* No report yet */}
      {!isLoading && !report && (
        <div className="py-4 text-center space-y-2">
          <Terminal className="w-8 h-8 text-ink-muted mx-auto" />
          <p className="text-sm text-ink-muted">No pulse report yet.</p>
          <p className="text-xs text-ink-muted">Run one manually or wait for Beat to trigger it.</p>
        </div>
      )}

      {/* Stats row */}
      {report && (
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-elevated rounded-md px-3 py-2 text-center">
            <div className="text-lg font-bold text-success mono">{report.stats.recent_renders}</div>
            <div className="text-xs text-ink-muted">Rendered</div>
          </div>
          <div className="bg-elevated rounded-md px-3 py-2 text-center">
            <div className={cn(
              "text-lg font-bold mono",
              report.stats.failed_contracts > 0 ? "text-danger" : "text-ink-secondary"
            )}>
              {report.stats.failed_contracts}
            </div>
            <div className="text-xs text-ink-muted">Failed</div>
          </div>
          <div className="bg-elevated rounded-md px-3 py-2 text-center">
            <div className="text-lg font-bold text-ink-primary mono">{report.stats.total_tracked_items}</div>
            <div className="text-xs text-ink-muted">Total</div>
          </div>
        </div>
      )}

      {/* Briefing text - collapsible */}
      {report && (
        <div className="space-y-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1.5 text-xs text-ink-muted hover:text-ink-primary transition-colors w-full"
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>Kernel briefing</span>
            {expanded
              ? <ChevronUp className="w-3.5 h-3.5 ml-auto" />
              : <ChevronDown className="w-3.5 h-3.5 ml-auto" />
            }
          </button>

          {expanded && (
            <pre className={cn(
              "text-xs text-ink-secondary mono whitespace-pre-wrap leading-relaxed",
              "bg-canvas rounded-md p-3 border border-border/50",
              "max-h-64 overflow-y-auto animate-fade-in"
            )}>
              {report.briefing}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}