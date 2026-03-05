"use client";

import { useState, useEffect, useRef } from "react";
import { useVentureStore } from "@/store";
import { useRunPipeline, usePipelineProgress } from "@/lib/hooks";
import { createPipelineWs } from "@/lib/api";
import {
  GitBranch, Play, CheckCircle2, XCircle, Clock,
  Loader2, Zap, ChevronRight, RefreshCw
} from "lucide-react";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";
import type { PipelineStep, WsPipelineMessage } from "@/types";

const STEP_STATUS_CONFIG = {
  completed:  { icon: CheckCircle2, color: "text-success", label: "Done"       },
  processing: { icon: Loader2,      color: "text-accent",  label: "Running"    },
  failed:     { icon: XCircle,      color: "text-danger",  label: "Failed"     },
  pending:    { icon: Clock,        color: "text-ink-muted", label: "Waiting"  },
};

function StepRow({ step, index }: { step: PipelineStep; index: number }) {
  const cfg = STEP_STATUS_CONFIG[step.status as keyof typeof STEP_STATUS_CONFIG]
    ?? STEP_STATUS_CONFIG.pending;
  const Icon = cfg.icon;

  return (
    <div className={cn(
      "flex items-center gap-3 py-2.5 px-3 rounded-md",
      "animate-slide-in-left transition-colors",
      step.status === "processing" && "bg-accent/5 border border-accent/10"
    )}
    style={{ animationDelay: `${index * 40}ms` }}
    >
      <Icon className={cn("w-4 h-4 flex-shrink-0", cfg.color,
        step.status === "processing" && "animate-spin"
      )} />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-ink-primary font-mono truncate">{step.step_id}</p>
        {step.topic && (
          <p className="text-xs text-ink-muted truncate">{step.topic}</p>
        )}
      </div>
      <span className={cn("text-xs font-medium flex-shrink-0", cfg.color)}>
        {cfg.label}
      </span>
    </div>
  );
}

export default function PipelinePage() {
  const activeVentureId = useVentureStore((s) => s.activeVentureId);
  const { mutate: runPipeline, isPending: isStarting } = useRunPipeline(activeVentureId ?? "");

  const [topic,      setTopic]      = useState("");
  const [campaignId, setCampaignId] = useState<number | null>(null);
  const [taskId,     setTaskId]     = useState<string | null>(null);
  const [wsSteps,    setWsSteps]    = useState<PipelineStep[]>([]);
  const [wsOverall,  setWsOverall]  = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Poll via REST as fallback (also used for initial load)
  const { data: pollData } = usePipelineProgress(
    activeVentureId,
    campaignId
  );

  // Use WebSocket steps if available, fall back to polled data
  const steps   = wsSteps.length > 0 ? wsSteps : (pollData?.steps ?? []);
  const overall = wsOverall ?? pollData?.overall ?? null;

  // Open WebSocket when we have a campaign ID
  useEffect(() => {
    if (!campaignId || !activeVentureId) return;

    const ws = createPipelineWs(activeVentureId, campaignId);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg: WsPipelineMessage = JSON.parse(event.data);
        setWsSteps(msg.steps);
        setWsOverall(msg.overall);
      } catch { /* ignore malformed messages */ }
    };

    ws.onerror = () => {
      // WebSocket failed — REST polling will take over automatically
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [campaignId, activeVentureId]);

  function handleRun() {
    if (!activeVentureId) return;

    runPipeline(
      { topic: topic.trim() || undefined },
      {
        onSuccess: (data) => {
          setCampaignId(data.campaign_id);
          setTaskId(data.task_id);
          setWsSteps([]);
          setWsOverall(null);
          toast.success("Pipeline queued.");
        },
        onError: () => toast.error("Failed to start pipeline."),
      }
    );
  }

  function handleReset() {
    setCampaignId(null);
    setTaskId(null);
    setWsSteps([]);
    setWsOverall(null);
    setTopic("");
    wsRef.current?.close();
  }

  const isRunning = overall === "running" || isStarting;

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-ink-primary">Pipeline</h1>
        <p className="text-sm text-ink-muted mt-0.5">
          Trigger a production run and watch it execute in real time.
        </p>
      </div>

      {/* Run form */}
      <div className="card p-5 space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <GitBranch className="w-4 h-4 text-ink-muted" />
          <h2 className="text-sm font-semibold text-ink-primary">New run</h2>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-ink-secondary uppercase tracking-widest">
            Topic <span className="text-ink-muted normal-case tracking-normal">(optional — leave blank for autonomous)</span>
          </label>
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="input-base"
            placeholder="e.g. Morning mobility for neck pain"
            disabled={isRunning}
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleRun}
            disabled={isRunning || !activeVentureId}
            className="btn-primary"
          >
            {isStarting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" fill="currentColor" />
            )}
            {isStarting ? "Queuing..." : "Run pipeline"}
          </button>

          {campaignId && (
            <button onClick={handleReset} className="btn-ghost text-ink-muted">
              <RefreshCw className="w-3.5 h-3.5" />
              New run
            </button>
          )}

          {taskId && (
            <span className="text-xs text-ink-muted font-mono">
              task: {taskId.slice(0, 8)}…
            </span>
          )}
        </div>
      </div>

      {/* Progress */}
      {campaignId && (
        <div className="card p-5 space-y-3 animate-slide-up">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-ink-primary">
                Campaign #{campaignId}
              </h2>
              {isRunning && (
                <span className="flex items-center gap-1.5 text-xs text-accent">
                  <Zap className="w-3 h-3 animate-pulse" />
                  Live
                </span>
              )}
            </div>

            {/* Overall status badge */}
            {overall && (
              <span className={cn(
                "text-xs px-2.5 py-1 rounded-full border font-medium capitalize",
                overall === "completed" && "text-success bg-success/10 border-success/20",
                overall === "running"   && "text-accent bg-accent/10 border-accent/20",
                overall === "failed"    && "text-danger bg-danger/10 border-danger/20",
                overall === "pending"   && "text-ink-muted bg-elevated border-border",
              )}>
                {overall}
              </span>
            )}
          </div>

          {/* Progress bar */}
          {steps.length > 0 && (
            <div className="w-full bg-elevated rounded-full h-1.5 overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  overall === "failed" ? "bg-danger" : "bg-accent"
                )}
                style={{
                  width: `${Math.round(
                    (steps.filter((s) => s.status === "completed").length / steps.length) * 100
                  )}%`,
                }}
              />
            </div>
          )}

          {/* Steps */}
          <div className="space-y-0.5">
            {steps.length === 0 ? (
              <div className="flex items-center gap-2 py-3 text-sm text-ink-muted">
                <Loader2 className="w-4 h-4 animate-spin text-accent" />
                Waiting for pipeline to start…
              </div>
            ) : (
              steps.map((step, i) => (
                <StepRow key={step.step_id} step={step} index={i} />
              ))
            )}
          </div>

          {overall === "completed" && (
            <div className="flex items-center gap-2 pt-2 text-sm text-success border-t border-border">
              <CheckCircle2 className="w-4 h-4" />
              Pipeline complete — check the queue for new items.
              <a href="/queue" className="ml-auto flex items-center gap-1 text-accent hover:text-accent-glow text-xs">
                Go to queue <ChevronRight className="w-3 h-3" />
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
