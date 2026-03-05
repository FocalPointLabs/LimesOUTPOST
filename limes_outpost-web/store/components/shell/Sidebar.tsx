"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, ListChecks, GitBranch,
  Building2, BarChart3, Zap, LogOut, Moon, Sun,
  Mail
} from "lucide-react";
import { useTheme } from "next-themes";
import { useAuthStore } from "@/store";
import { VentureSwitcher } from "./VentureSwitcher";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { label: "Dashboard",  href: "/",          icon: LayoutDashboard },
  { label: "Inbox",      href: "/inbox",      icon: Mail            },
  { label: "Queue",      href: "/queue",      icon: ListChecks      },
  { label: "Pipeline",   href: "/pipeline",   icon: GitBranch       },
  { label: "Analytics",  href: "/analytics",  icon: BarChart3       },
  { label: "Ventures",   href: "/ventures",   icon: Building2       },
];

export function Sidebar() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const { user, logout }    = useAuthStore();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <aside className="w-56 flex-shrink-0 flex flex-col h-screen bg-surface border-r border-border">
      {/* Logo */}
      <div className="px-4 pt-5 pb-4 flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center shadow-glow-sm">
          <Zap className="w-3.5 h-3.5 text-white" fill="currentColor" />
        </div>
        <span className="text-base font-bold tracking-tight text-ink-primary">
          LimesOutpost<span className="text-accent">.</span>
        </span>
      </div>

      {/* Venture switcher */}
      <div className="px-3 pb-3 border-b border-border">
        <VentureSwitcher />
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS.map(({ label, href, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium",
              "transition-all duration-100",
              isActive(href)
                ? "bg-accent/10 text-accent border-l-2 border-accent pl-[10px]"
                : "text-ink-secondary hover:text-ink-primary hover:bg-elevated"
            )}
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </Link>
        ))}
      </nav>

      {/* Bottom: user + theme toggle */}
      <div className="px-3 py-3 border-t border-border space-y-1">
        {/* Theme toggle */}
      <button
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        className="btn-ghost w-full justify-start text-ink-muted"
        suppressHydrationWarning
      >
        <span suppressHydrationWarning>
          {theme === "dark"
            ? <Sun  className="w-4 h-4" />
            : <Moon className="w-4 h-4" />
          }
        </span>
        <span suppressHydrationWarning>
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </span>
      </button>

        {/* User */}
        <div className="flex items-center gap-2 px-3 py-2 rounded-md">
          <div className="w-6 h-6 rounded-full bg-accent/20 flex items-center justify-center flex-shrink-0">
            <span className="text-xs font-bold text-accent">
              {user?.email?.[0]?.toUpperCase() ?? "?"}
            </span>
          </div>
          <span className="text-xs text-ink-muted font-mono truncate flex-1 min-w-0">
            {user?.email ?? "—"}
          </span>
          <button
            onClick={logout}
            className="text-ink-muted hover:text-danger transition-colors"
            title="Sign out"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}