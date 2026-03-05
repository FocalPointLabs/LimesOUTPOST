"use client";

import { use, useState, useEffect } from "react";
import { useVenture, usePatchVenture } from "@/lib/hooks";
import { Save, Loader2, Clock, Users, Shield, ChevronDown, ChevronUp, Check } from "lucide-react";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";
import { venturesApi } from "@/lib/api";

const WORKFLOW_OPTIONS = [
  { key: "short_form_video", label: "Short-form video",        defaultCron: "0 9 * * *"   },
  { key: "blog_post",        label: "Blog posts",              defaultCron: "0 10 * * 1"  },
  { key: "email",            label: "Email inbox cycle",       defaultCron: "0 */2 * * *" },
  { key: "social_reply",     label: "Social replies",          defaultCron: "0 12 * * *"  },
  { key: "analytics",        label: "Analytics pull",          defaultCron: "0 6 * * *"   },
  { key: "publish",          label: "Auto-publish approved",   defaultCron: "*/30 * * * *"},
];

type Section = "schedule" | "brand" | "members";

export default function VentureSettingsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id }                 = use(params);
  const { data: venture, isLoading } = useVenture(id);
  const { mutate: patch, isPending } = usePatchVenture(id);

  const [open, setOpen] = useState<Section>("schedule");

  // Schedule state
  const [schedule, setSchedule] = useState<Record<string, { cron: string; enabled: boolean }>>({});

  // Brand state
  const [brandJson, setBrandJson] = useState("");
  const [brandError, setBrandError] = useState("");

  // Members state
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole,  setInviteRole]  = useState<"operator" | "viewer">("operator");
  const [inviting,    setInviting]    = useState(false);

  useEffect(() => {
    if (!venture) return;
    setSchedule(
      Object.fromEntries(
        WORKFLOW_OPTIONS.map(({ key, defaultCron }) => [
          key,
          venture.workflow_schedule[key] ?? { cron: defaultCron, enabled: false },
        ])
      )
    );
    setBrandJson(JSON.stringify(venture.brand_profile, null, 2));
  }, [venture]);

  function saveSchedule() {
    patch(
      { workflow_schedule: schedule },
      {
        onSuccess: () => toast.success("Schedule saved. Restart Beat to apply."),
        onError:   () => toast.error("Failed to save schedule."),
      }
    );
  }

  function saveBrand() {
    try {
      const parsed = JSON.parse(brandJson);
      setBrandError("");
      patch(
        { brand_profile: parsed },
        {
          onSuccess: () => toast.success("Brand profile saved."),
          onError:   () => toast.error("Failed to save brand profile."),
        }
      );
    } catch {
      setBrandError("Invalid JSON — check your syntax.");
    }
  }

  async function inviteMember() {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      await venturesApi.inviteMember(id, inviteEmail.trim(), inviteRole);
      toast.success(`${inviteEmail} added as ${inviteRole}.`);
      setInviteEmail("");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? "Failed to invite member.";
      toast.error(msg);
    } finally {
      setInviting(false);
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-16 rounded-lg bg-elevated animate-pulse" />
        ))}
      </div>
    );
  }

  if (!venture) {
    return (
      <div className="card p-8 text-center text-ink-muted">
        Venture not found or access denied.
      </div>
    );
  }

  const sections: { key: Section; label: string; icon: React.ElementType }[] = [
    { key: "schedule", label: "Workflow schedule", icon: Clock   },
    { key: "brand",    label: "Brand profile",     icon: Shield  },
    { key: "members",  label: "Team members",      icon: Users   },
  ];

  return (
    <div className="max-w-2xl space-y-4 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-ink-primary">{venture.name}</h1>
        <p className="text-xs text-ink-muted font-mono mt-0.5">{venture.id} · {venture.timezone}</p>
      </div>

      {/* Accordion sections */}
      {sections.map(({ key, label, icon: Icon }) => (
        <div key={key} className="card overflow-hidden">
          {/* Accordion header */}
          <button
            onClick={() => setOpen(open === key ? ("" as Section) : key)}
            className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-elevated/30 transition-colors"
          >
            <div className="flex items-center gap-2.5">
              <Icon className="w-4 h-4 text-ink-muted" />
              <span className="text-sm font-semibold text-ink-primary">{label}</span>
            </div>
            {open === key
              ? <ChevronUp   className="w-4 h-4 text-ink-muted" />
              : <ChevronDown className="w-4 h-4 text-ink-muted" />
            }
          </button>

          {/* Schedule section */}
          {open === "schedule" && key === "schedule" && (
            <div className="px-5 pb-5 space-y-3 border-t border-border pt-4">
              {WORKFLOW_OPTIONS.map(({ key: wKey, label: wLabel }) => (
                <div key={wKey} className={cn(
                  "flex items-center gap-3 p-3 rounded-md border transition-all",
                  schedule[wKey]?.enabled
                    ? "border-accent/20 bg-accent/5"
                    : "border-border bg-elevated/30"
                )}>
                  {/* Toggle */}
                  <button
                    onClick={() => setSchedule((prev) => ({
                      ...prev,
                      [wKey]: { ...prev[wKey], enabled: !prev[wKey]?.enabled }
                    }))}
                    className={cn(
                      "w-8 h-4.5 rounded-full transition-all duration-200 flex-shrink-0 relative",
                      schedule[wKey]?.enabled ? "bg-accent" : "bg-border"
                    )}
                    style={{ height: "18px", width: "32px" }}
                  >
                    <span className={cn(
                      "absolute top-0.5 left-0.5 w-3.5 h-3.5 rounded-full bg-white transition-transform duration-200",
                      schedule[wKey]?.enabled && "translate-x-[14px]"
                    )} />
                  </button>

                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-ink-primary">{wLabel}</p>
                    <input
                      value={schedule[wKey]?.cron ?? ""}
                      onChange={(e) => setSchedule((prev) => ({
                        ...prev,
                        [wKey]: { ...prev[wKey], cron: e.target.value }
                      }))}
                      className="text-xs font-mono text-ink-muted bg-transparent border-none outline-none w-full mt-0.5"
                      placeholder="cron expression"
                      disabled={!schedule[wKey]?.enabled}
                    />
                  </div>

                  {schedule[wKey]?.enabled && (
                    <Check className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                  )}
                </div>
              ))}

              <div className="flex justify-end pt-1">
                <button onClick={saveSchedule} disabled={isPending} className="btn-primary text-sm">
                  {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Save schedule
                </button>
              </div>

              <p className="text-xs text-ink-muted">
                After saving, restart the Beat container for changes to take effect:{" "}
                <span className="font-mono bg-elevated px-1 py-0.5 rounded">
                  docker compose restart celery_beat
                </span>
              </p>
            </div>
          )}

          {/* Brand profile section */}
          {open === "brand" && key === "brand" && (
            <div className="px-5 pb-5 space-y-3 border-t border-border pt-4">
              <p className="text-xs text-ink-muted">
                Edit the raw brand profile JSON. This is passed as context to every agent in the pipeline.
              </p>
              <textarea
                value={brandJson}
                onChange={(e) => { setBrandJson(e.target.value); setBrandError(""); }}
                className={cn(
                  "input-base font-mono text-xs min-h-64 resize-y",
                  brandError && "border-danger/50"
                )}
                spellCheck={false}
              />
              {brandError && (
                <p className="text-xs text-danger">{brandError}</p>
              )}
              <div className="flex justify-end">
                <button onClick={saveBrand} disabled={isPending} className="btn-primary text-sm">
                  {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Save brand profile
                </button>
              </div>
            </div>
          )}

          {/* Members section */}
          {open === "members" && key === "members" && (
            <div className="px-5 pb-5 space-y-4 border-t border-border pt-4">
              <div className="flex items-center gap-2">
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="input-base flex-1"
                  placeholder="teammate@example.com"
                />
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as "operator" | "viewer")}
                  className="input-base w-32"
                >
                  <option value="operator">Operator</option>
                  <option value="viewer">Viewer</option>
                </select>
                <button
                  onClick={inviteMember}
                  disabled={inviting || !inviteEmail.trim()}
                  className="btn-primary text-sm flex-shrink-0"
                >
                  {inviting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Invite"}
                </button>
              </div>
              <p className="text-xs text-ink-muted">
                The user must have an existing LimesOutpost account. Operators can trigger pipelines and approve queue items. Viewers have read-only access.
              </p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}