"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Check, Plus, Zap } from "lucide-react";
import { useVentureStore } from "@/store";
import { useVentures } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { Venture } from "@/types";

const STATUS_COLORS: Record<string, string> = {
  active:   "bg-success",
  paused:   "bg-warning",
  archived: "bg-neutral",
};

export function VentureSwitcher() {
  const qc                = useQueryClient();
  const { data: ventures, isLoading } = useVentures();
  const activeVentureId   = useVentureStore((s) => s.activeVentureId);
  const setActiveVenture  = useVentureStore((s) => s.setActiveVenture);
  const [open, setOpen]   = useState(false);

  const active = ventures?.find((v) => v.id === activeVentureId);

  function handleSelect(venture: Venture) {
    if (venture.id === activeVentureId) {
      setOpen(false);
      return;
    }

    setActiveVenture(venture.id);
    setOpen(false);

    // Invalidate all venture-scoped queries so nothing stale leaks
    // This is the key multi-tenant safety guarantee:
    // every query keyed by ventureId will refetch for the new venture.
    qc.invalidateQueries({ predicate: (query) => {
      const key = query.queryKey;
      // Keep ventures list and user — invalidate everything else
      return Array.isArray(key) && !["ventures", "me"].includes(key[0] as string);
    }});
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 rounded-md bg-elevated border border-border animate-pulse">
        <div className="w-5 h-5 rounded bg-border" />
        <div className="w-24 h-3 rounded bg-border" />
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          "flex items-center gap-2.5 px-3 py-2 rounded-md w-full",
          "bg-elevated border transition-all duration-150",
          open
            ? "border-accent/40 shadow-glow-sm"
            : "border-border hover:border-border/80"
        )}
      >
        {/* Venture icon */}
        <div className="w-6 h-6 rounded bg-accent/20 flex items-center justify-center flex-shrink-0">
          <Zap className="w-3 h-3 text-accent" />
        </div>

        {/* Name + status */}
        <div className="flex-1 text-left min-w-0">
          <div className="text-sm font-semibold text-ink-primary truncate leading-none mb-0.5">
            {active?.name ?? "Select venture"}
          </div>
          {active && (
            <div className="flex items-center gap-1.5">
              <span className={cn("status-dot w-1.5 h-1.5", STATUS_COLORS[active.status] ?? "bg-neutral")} />
              <span className="text-xs text-ink-muted font-mono capitalize">{active.status}</span>
            </div>
          )}
        </div>

        <ChevronDown className={cn(
          "w-3.5 h-3.5 text-ink-muted transition-transform duration-150 flex-shrink-0",
          open && "rotate-180"
        )} />
      </button>

      {/* Dropdown */}
      {open && (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />

          <div className={cn(
            "absolute top-full left-0 right-0 mt-1 z-50",
            "bg-elevated border border-border rounded-lg shadow-elevated",
            "animate-slide-up overflow-hidden"
          )}>
            {ventures && ventures.length > 0 ? (
              <div className="py-1">
                {ventures.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => handleSelect(v)}
                    className={cn(
                      "w-full flex items-center gap-2.5 px-3 py-2.5",
                      "text-left transition-colors duration-100",
                      v.id === activeVentureId
                        ? "bg-accent/10 text-ink-primary"
                        : "hover:bg-surface text-ink-secondary hover:text-ink-primary"
                    )}
                  >
                    <div className="w-5 h-5 rounded bg-accent/10 flex items-center justify-center flex-shrink-0">
                      <Zap className="w-2.5 h-2.5 text-accent" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{v.name}</div>
                      <div className="text-xs text-ink-muted font-mono">{v.id}</div>
                    </div>
                    {v.id === activeVentureId && (
                      <Check className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            ) : (
              <div className="px-3 py-4 text-center text-sm text-ink-muted">
                No ventures yet
              </div>
            )}

            {/* Add new */}
            <div className="border-t border-border">
              <a
                href="/ventures/new"
                className="flex items-center gap-2 px-3 py-2.5 text-sm text-ink-muted hover:text-accent hover:bg-surface transition-colors"
                onClick={() => setOpen(false)}
              >
                <Plus className="w-4 h-4" />
                New venture
              </a>
            </div>
          </div>
        </>
      )}
    </div>
  );
}