"use client";

import { useVentureStore } from "@/store";
import { useVentures } from "@/lib/hooks";
import { Building2, Plus, ArrowRight, Zap, Users, Clock } from "lucide-react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import type { Venture } from "@/types";

const STATUS_CONFIG = {
  active:   { label: "Active",   color: "text-success", dot: "bg-success" },
  paused:   { label: "Paused",   color: "text-warning", dot: "bg-warning" },
  archived: { label: "Archived", color: "text-neutral", dot: "bg-neutral" },
};

function VentureCard({ venture }: { venture: Venture }) {
  const setActive      = useVentureStore((s) => s.setActiveVenture);
  const activeId       = useVentureStore((s) => s.activeVentureId);
  const isActive       = venture.id === activeId;
  const cfg            = STATUS_CONFIG[venture.status] ?? STATUS_CONFIG.active;
  const scheduleCount  = Object.values(venture.workflow_schedule).filter((w) => w?.enabled).length;

  return (
    <div className={cn(
      "card p-5 flex flex-col gap-4 transition-all duration-200",
      isActive && "border-accent/30 shadow-glow-sm"
    )}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <div className={cn(
            "w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0",
            isActive ? "bg-accent/20" : "bg-elevated"
          )}>
            <Zap className={cn("w-4 h-4", isActive ? "text-accent" : "text-ink-muted")} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-ink-primary">{venture.name}</h3>
            <p className="text-xs text-ink-muted font-mono">{venture.id}</p>
          </div>
        </div>
        <span className={cn(
          "text-xs flex items-center gap-1.5 flex-shrink-0",
          cfg.color
        )}>
          <span className={cn("w-1.5 h-1.5 rounded-full", cfg.dot)} />
          {cfg.label}
        </span>
      </div>

      {/* Meta */}
      <div className="flex items-center gap-4 text-xs text-ink-muted">
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {scheduleCount} workflow{scheduleCount !== 1 ? "s" : ""} scheduled
        </span>
        <span className="flex items-center gap-1">
          <Users className="w-3 h-3" />
          {venture.role}
        </span>
        <span className="font-mono">{venture.timezone}</span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1 border-t border-border">
        {!isActive && (
          <button
            onClick={() => setActive(venture.id)}
            className="btn-primary text-xs py-1.5 px-3"
          >
            <Zap className="w-3 h-3" />
            Switch to
          </button>
        )}
        {isActive && (
          <span className="text-xs text-accent flex items-center gap-1.5">
            <Zap className="w-3 h-3" fill="currentColor" />
            Currently active
          </span>
        )}
        <Link
          href={`/ventures/${venture.id}`}
          className="btn-ghost text-xs ml-auto"
        >
          Settings <ArrowRight className="w-3 h-3" />
        </Link>
      </div>
    </div>
  );
}

export default function VenturesPage() {
  const { data: ventures, isLoading } = useVentures();

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-ink-primary">Ventures</h1>
          <p className="text-sm text-ink-muted mt-0.5">
            {ventures ? `${ventures.length} venture${ventures.length !== 1 ? "s" : ""}` : "—"}
          </p>
        </div>
        <Link href="/ventures/new" className="btn-primary">
          <Plus className="w-4 h-4" />
          New venture
        </Link>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="h-44 rounded-lg bg-elevated animate-pulse" />
          ))}
        </div>
      ) : ventures?.length === 0 ? (
        <div className="card p-12 text-center space-y-4">
          <Building2 className="w-10 h-10 text-ink-muted mx-auto opacity-40" />
          <div>
            <p className="text-ink-primary font-semibold">No ventures yet</p>
            <p className="text-sm text-ink-muted mt-1">
              Create your first venture to get started.
            </p>
          </div>
          <Link href="/ventures/new" className="btn-primary inline-flex">
            <Plus className="w-4 h-4" /> Create venture
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {ventures?.map((v) => (
            <VentureCard key={v.id} venture={v} />
          ))}
        </div>
      )}
    </div>
  );
}
