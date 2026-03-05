"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, pipelineApi } from "@/lib/api";
import { Zap, RefreshCw, ChevronDown, ChevronUp, Terminal, Activity, AlertTriangle } from "lucide-react";
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

export function PulseCard({ ventureId }: { ventureId: string }) {
  const [expanded, setExpanded] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [lastReportId, setLastReportId] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["pulse", ventureId],
    queryFn: () => fetchLatestPulse(ventureId),
    enabled: !!ventureId,
    refetchInterval: isPolling ? 2000 : 60_000,
  });

  const report = data?.report;

  useEffect(() => {
    if (isPolling && report && report.id !== lastReportId) {
      setIsPolling(false);
      setLastReportId(report.id);
    }
  }, [report, isPolling, lastReportId]);

  const { mutate: runPulse, isPending } = useMutation({
    mutationFn: () => pipelineApi.pulse(ventureId),
    onSuccess: () => {
      setLastReportId(report?.id || null);
      setIsPolling(true);
    },
  });

  const isUpdating = isPending || isPolling;

  // Health calculation
  const total      = report?.stats.total_tracked_items || 0;
  const success    = report?.stats.recent_renders || 0;
  const healthRate = total > 0 ? Math.round((success / total) * 100) : 100;
  const hasBlockers = (report?.stats.failed_contracts || 0) > 0;
  const isWarning   = healthRate < 100 && !hasBlockers;

  // Theme — transparent borders so they breathe on dark surfaces
  // Full border-color tokens, not opacity hacks that vanish on dark bg
  const theme = {
    border: hasBlockers
      ? "border-danger/40"
      : isWarning
        ? "border-warning/35"
        : "border-accent/25",
    iconBg: hasBlockers ? "bg-danger/15"  : isWarning ? "bg-warning/15"  : "bg-accent/15",
    text:   hasBlockers ? "text-danger"   : isWarning ? "text-warning"   : "text-accent",
  };

  return (
    <div className={cn(
      "card p-4 space-y-3 transition-all duration-500",
      theme.border
    )}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className={cn("w-7 h-7 rounded-md flex items-center justify-center", theme.iconBg)}>
            <Zap
              className={cn(
                "w-3.5 h-3.5",
                theme.text,
                (isUpdating || hasBlockers || isWarning) && "animate-pulse"
              )}
              fill="currentColor"
            />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-ink-primary">Assistant Pulse</h2>
            {report ? (
              <p className="text-xs text-ink-muted mono">
                {formatDistanceToNow(new Date(report.created_at), { addSuffix: true })}
              </p>
            ) : (
              <p className="text-xs text-ink-muted">No report yet</p>
            )}
          </div>
        </div>

        <button
          onClick={() => runPulse()}
          disabled={isUpdating}
          className="btn-ghost text-xs gap-1.5"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", isUpdating && "animate-spin")} />
          {isUpdating ? "Consulting..." : "Run check"}
        </button>
      </div>

      {/* Stat mini-cards */}
      {report && (
        <div className="grid grid-cols-2 gap-2">
          {/* Health */}
          <div className="bg-elevated rounded-md px-3 py-2.5 border border-border">
            <div className="flex items-center gap-1.5 mb-1">
              <Activity className={cn(
                "w-3 h-3",
                healthRate === 100 ? "text-success" : "text-warning"
              )} />
              <span className="text-xs text-ink-secondary">Health</span>
            </div>
            <div className={cn(
              "text-lg font-bold mono leading-none",
              healthRate === 100 ? "text-success" : "text-warning"
            )}>
              {healthRate}%
            </div>
          </div>

          {/* Blockers — elevated base with danger tint when relevant */}
          <div className={cn(
            "rounded-md px-3 py-2.5 border",
            hasBlockers
              ? "bg-danger/8 border-danger/35"
              : "bg-elevated border-border"
          )}>
            <div className="flex items-center gap-1.5 mb-1">
              <AlertTriangle className={cn(
                "w-3 h-3",
                hasBlockers ? "text-danger" : "text-ink-secondary"
              )} />
              <span className="text-xs text-ink-secondary">Blockers</span>
            </div>
            <div className={cn(
              "text-lg font-bold mono leading-none",
              hasBlockers ? "text-danger" : "text-ink-primary"
            )}>
              {report.stats.failed_contracts}
            </div>
          </div>
        </div>
      )}

      {/* Assistant Briefing */}
      {report && (
        <div className="space-y-1.5">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1.5 text-xs text-ink-secondary hover:text-ink-primary transition-colors w-full"
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>Assistant briefing</span>
            {expanded
              ? <ChevronUp className="w-3.5 h-3.5 ml-auto" />
              : <ChevronDown className="w-3.5 h-3.5 ml-auto" />
            }
          </button>

          {expanded && (
            // .briefing-box from globals: gradient accent/sage bg, left accent stripe,
            // sits at mid-depth — doesn't punch a dark hole inside the card
            <pre className={cn(
              "briefing-box animate-fade-in",
              "max-h-64 overflow-y-auto text-ink-primary",
              isUpdating && "opacity-50"
            )}>
              {report.briefing}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}