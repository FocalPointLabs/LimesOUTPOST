"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import toast from "react-hot-toast";
import { Zap, Mail, Lock, ArrowRight, Loader2 } from "lucide-react";
import { authApi, setTokens } from "@/lib/api";
import { useAuthStore } from "@/store";
import { cn } from "@/lib/utils";

export default function LoginPage() {
  const router  = useRouter();
  const login   = useAuthStore((s) => s.login);

  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const { data: tokens } = await authApi.login(email, password);
      // Set tokens before fetching user so the interceptor has them
      setTokens(tokens.access_token, tokens.refresh_token);
      // Also set cookie for middleware
      document.cookie = `ff_access=${tokens.access_token}; path=/; max-age=3600; SameSite=Lax`;

      const { data: user } = await authApi.me();
      login(tokens.access_token, tokens.refresh_token, user);

      toast.success("Welcome back.");
      router.push("/");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? "Invalid email or password.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="animate-slide-up">
      {/* Logo */}
      <div className="flex items-center gap-2 mb-10">
        <div className="w-8 h-8 rounded-md bg-accent flex items-center justify-center shadow-glow-sm">
          <Zap className="w-4 h-4 text-white" fill="currentColor" />
        </div>
        <span className="text-lg font-bold tracking-tight text-ink-primary">
          LimesOutpost<span className="text-accent">.</span>
        </span>
      </div>

      <div className="card p-6 space-y-6">
        <div>
          <h1 className="text-xl font-bold text-ink-primary">Sign in</h1>
          <p className="text-sm text-ink-secondary mt-1">
            Back to the control room.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Email */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-ink-secondary uppercase tracking-widest">
              Email
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-muted" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input-base pl-9"
                placeholder="you@example.com"
                required
                autoComplete="email"
              />
            </div>
          </div>

          {/* Password */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-ink-secondary uppercase tracking-widest">
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-muted" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-base pl-9"
                placeholder="••••••••"
                required
                autoComplete="current-password"
              />
            </div>
          </div>

          {/* Error */}
          {error && (
            <p className="text-xs text-danger bg-danger/10 border border-danger/20 rounded-md px-3 py-2">
              {error}
            </p>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className={cn("btn-primary w-full", loading && "opacity-70")}
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                Sign in
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        <p className="text-center text-sm text-ink-muted">
          No account?{" "}
          <Link href="/register" className="text-accent hover:text-accent-glow transition-colors">
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}
