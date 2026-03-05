"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useCreateVenture } from "@/lib/hooks";
import { useVentureStore } from "@/store";
import { ArrowRight, ArrowLeft, Zap, Loader2, Check } from "lucide-react";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";

const STEPS = ["Identity", "Brand", "Schedule"] as const;

const TIMEZONES = [
  "UTC", "America/New_York", "America/Chicago",
  "America/Denver", "America/Los_Angeles",
  "Europe/London", "Europe/Paris", "Asia/Tokyo", "Asia/Sydney",
];

const WORKFLOW_OPTIONS = [
  { key: "short_form_video", label: "Short-form video",  desc: "YouTube Shorts, TikTok-style content" },
  { key: "blog_post",        label: "Blog posts",        desc: "Long-form written content"            },
  { key: "email",            label: "Email management",  desc: "Inbox triage and reply drafting"      },
  { key: "social_reply",     label: "Social replies",    desc: "Automated engagement and replies"     },
  { key: "analytics",        label: "Analytics pull",    desc: "Daily YouTube Analytics fetch"        },
];

const DEFAULT_CRONS: Record<string, string> = {
  short_form_video: "0 9 * * *",
  blog_post:        "0 10 * * 1",
  email:            "0 8 * * *",
  analytics:        "0 6 * * *",
};

export default function NewVenturePage() {
  const router         = useRouter();
  const { mutate: createVenture, isPending } = useCreateVenture();
  const setActive      = useVentureStore((s) => s.setActiveVenture);

  const [step, setStep]   = useState(0);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Step 0 — Identity
  const [id,       setId]       = useState("");
  const [name,     setName]     = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [personalProfile, setPersonalProfile] = useState({
    role_title: "Founder",
    communication_style: "Direct & Efficient",
    interests: ""
  });

  // Step 1 — Brand
  const [niche,       setNiche]       = useState("");
  const [description, setDescription] = useState("");
  const [approved,    setApproved]    = useState("");
  const [banned,      setBanned]      = useState("");

  // Step 2 — Schedule
  const [enabled, setEnabled] = useState<Record<string, boolean>>({
    short_form_video: true,
    blog_post:        true,
    email:            false,
    analytics:        true,
  });

  function validateStep0() {
    const e: Record<string, string> = {};
    if (!id.trim())   e.id   = "Venture ID is required.";
    if (!/^[a-z0-9-]+$/.test(id.trim())) e.id = "ID must be lowercase letters, numbers, and hyphens only.";
    if (!name.trim()) e.name = "Name is required.";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function validateStep1() {
    const e: Record<string, string> = {};
    if (!niche.trim()) e.niche = "Niche is required.";
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function next() {
    if (step === 0 && !validateStep0()) return;
    if (step === 1 && !validateStep1()) return;
    setErrors({});
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  }

  function submit() {
    const workflow_schedule: Record<string, { cron: string; enabled: boolean }> = {};
    for (const [key, isEnabled] of Object.entries(enabled)) {
      workflow_schedule[key] = { cron: DEFAULT_CRONS[key], enabled: isEnabled };
    }

    const brand_profile = {
      venture_id:  id.trim(),
      name:        name.trim(),
      niche:       niche.trim(),
      description: description.trim(),
      rules: {
        approved_vocabulary: approved.split(",").map((s) => s.trim()).filter(Boolean),
        banned_vocabulary:   banned.split(",").map((s) => s.trim()).filter(Boolean),
      },
    };

    createVenture(
      { 
        id: id.trim(), 
        name: name.trim(), 
        brand_profile, 
        timezone,
        personal_profile: personalProfile 
      },
      {
        onSuccess: (venture) => {
          setActive(venture.id);
          toast.success(`Venture '${venture.name}' established.`);
          router.push("/");
        },
        onError: (err: unknown) => {
          const msg = (err as { response?: { data?: { detail?: string } } })
            ?.response?.data?.detail ?? "Failed to create venture.";
          toast.error(msg);
        },
      }
    );
  }

  return (
    <div className="max-w-xl animate-fade-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-ink-primary">New venture</h1>
        <p className="text-sm text-ink-muted mt-0.5">
          Provision a new autonomous content venture.
        </p>
      </div>

      <div className="flex items-center gap-2 mb-6">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <div className={cn(
              "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-all",
              i < step  && "bg-success text-white",
              i === step && "bg-accent text-white shadow-glow-sm",
              i > step  && "bg-elevated text-ink-muted border border-border",
            )}>
              {i < step ? <Check className="w-3 h-3" /> : i + 1}
            </div>
            <span className={cn(
              "text-xs font-medium",
              i === step ? "text-ink-primary" : "text-ink-muted"
            )}>
              {label}
            </span>
            {i < STEPS.length - 1 && (
              <div className={cn(
                "w-8 h-px mx-1",
                i < step ? "bg-success" : "bg-border"
              )} />
            )}
          </div>
        ))}
      </div>

      <div className="card p-6 space-y-5">
        {step === 0 && (
          <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2">
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink-muted">Venture Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className={cn("input-base mt-1", errors.name && "border-danger/50")}
                placeholder="e.g. Alpha Growth Labs"
              />
              {errors.name && <p className="text-xs text-danger">{errors.name}</p>}
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-ink-secondary uppercase tracking-widest">
                Venture ID
              </label>
              <input
                value={id}
                onChange={(e) => setId(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                className={cn("input-base", errors.id && "border-danger/50")}
                placeholder="yoga-zen-001"
              />
              {errors.id && <p className="text-xs text-danger">{errors.id}</p>}
              <p className="text-xs text-ink-muted">Lowercase, hyphens only.</p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-bold uppercase tracking-wider text-ink-muted">Your Role</label>
                <input
                  value={personalProfile.role_title}
                  onChange={(e) => setPersonalProfile({...personalProfile, role_title: e.target.value})}
                  className="input-base mt-1"
                  placeholder="e.g. CEO, Visionary"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-bold uppercase tracking-wider text-ink-muted">Voice Style</label>
                <select
                  value={personalProfile.communication_style}
                  onChange={(e) => setPersonalProfile({...personalProfile, communication_style: e.target.value})}
                  className="input-base mt-1"
                >
                  <option value="Direct & Efficient">Direct & Efficient</option>
                  <option value="Inspirational">Inspirational</option>
                  <option value="Analytical">Analytical</option>
                  <option value="Aggressive">Aggressive</option>
                </select>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink-muted">Timezone</label>
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="input-base mt-1"
              >
                {TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4 animate-slide-up">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-ink-secondary uppercase tracking-widest">
                Niche
              </label>
              <input
                value={niche}
                onChange={(e) => setNiche(e.target.value)}
                className={cn("input-base", errors.niche && "border-danger/50")}
                placeholder="Yoga & Mindfulness"
              />
              {errors.niche && <p className="text-xs text-danger">{errors.niche}</p>}
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-ink-secondary uppercase tracking-widest">
                Brand description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="input-base min-h-20 resize-none"
                placeholder="A calm, expert voice in the wellness space..."
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-ink-secondary uppercase tracking-widest">
                Approved vocabulary
              </label>
              <input
                value={approved}
                onChange={(e) => setApproved(e.target.value)}
                className="input-base"
                placeholder="mindful, nourish, flow, restore"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-ink-secondary uppercase tracking-widest">
                Banned vocabulary
              </label>
              <input
                value={banned}
                onChange={(e) => setBanned(e.target.value)}
                className="input-base"
                placeholder="crush, hustle, grind"
              />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3 animate-slide-up">
            <p className="text-sm text-ink-secondary">
              Select which workflows Beat should run automatically.
            </p>
            {WORKFLOW_OPTIONS.map(({ key, label, desc }) => (
              <label key={key} className={cn(
                "flex items-start gap-3 p-3 rounded-md border cursor-pointer transition-all",
                enabled[key]
                  ? "border-accent/30 bg-accent/5"
                  : "border-border hover:border-border/80 bg-elevated/30"
              )}>
                <div className="relative flex-shrink-0 mt-0.5">
                  <input
                    type="checkbox"
                    checked={enabled[key] ?? false}
                    onChange={(e) => setEnabled((prev) => ({ ...prev, [key]: e.target.checked }))}
                    className="sr-only"
                  />
                  <div className={cn(
                    "w-4 h-4 rounded border-2 flex items-center justify-center transition-all",
                    enabled[key] ? "bg-accent border-accent" : "border-border"
                  )}>
                    {enabled[key] && <Check className="w-2.5 h-2.5 text-white" />}
                  </div>
                </div>
                <div>
                  <p className="text-sm font-medium text-ink-primary">{label}</p>
                  <p className="text-xs text-ink-muted">{desc}</p>
                  <p className="text-xs text-ink-muted font-mono mt-0.5">{DEFAULT_CRONS[key]}</p>
                </div>
              </label>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between pt-2 border-t border-border">
          <button
            onClick={() => setStep((s) => Math.max(s - 1, 0))}
            disabled={step === 0}
            className="btn-ghost disabled:opacity-0"
          >
            <ArrowLeft className="w-4 h-4" /> Back
          </button>

          {step < STEPS.length - 1 ? (
            <button onClick={next} className="btn-primary">
              Next <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button onClick={submit} disabled={isPending} className="btn-primary">
              {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              {isPending ? "Creating…" : "Create venture"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}