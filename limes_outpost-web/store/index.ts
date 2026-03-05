// store/index.ts
// Thin client state only. Server state lives in React Query.
// Two slices: auth (user + tokens) and venture (active venture context).

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { User, Venture } from "@/types";
import { clearTokens, setTokens } from "@/lib/api";

// ── Auth slice ────────────────────────────────────────────────
interface AuthState {
  user:      User | null;
  isAuthed:  boolean;
  setUser:   (user: User) => void;
  login:     (access: string, refresh: string, user: User) => void;
  logout:    () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user:     null,
      isAuthed: false,

      setUser: (user) => set({ user, isAuthed: true }),

      login: (access, refresh, user) => {
        setTokens(access, refresh);
        set({ user, isAuthed: true });
      },

      logout: () => {
        clearTokens();
        set({ user: null, isAuthed: false });
      },
    }),
    {
      name:    "ff_auth",
      storage: createJSONStorage(() => localStorage),
      // Only persist user identity, not sensitive tokens
      // Tokens are stored separately in localStorage by api.ts
      partialize: (state) => ({ user: state.user, isAuthed: state.isAuthed }),
    }
  )
);

// ── Venture slice ─────────────────────────────────────────────
// This is the load-bearing piece for multi-tenant context.
// activeVentureId is the single source of truth.
// All data-fetching hooks key off this value.
// Switching ventures here invalidates all downstream queries automatically
// because React Query keys include ventureId.

interface VentureState {
  activeVentureId:  string | null;
  // Cached venture list for the switcher (populated by useVentures query)
  ventures:         Venture[];

  setActiveVenture: (id: string) => void;
  setVentures:      (ventures: Venture[]) => void;
  clearVenture:     () => void;
}

export const useVentureStore = create<VentureState>()(
  persist(
    (set) => ({
      activeVentureId: null,
      ventures:        [],

      setActiveVenture: (id) => set({ activeVentureId: id }),

      setVentures: (ventures) => set((state) => ({
        ventures,
        // Auto-select first venture if none selected, or if selected one no longer exists
        activeVentureId:
          state.activeVentureId && ventures.some((v) => v.id === state.activeVentureId)
            ? state.activeVentureId
            : ventures[0]?.id ?? null,
      })),

      clearVenture: () => set({ activeVentureId: null, ventures: [] }),
    }),
    {
      name:    "ff_venture",
      storage: createJSONStorage(() => localStorage),
      // Persist active venture selection across sessions
      partialize: (state) => ({ activeVentureId: state.activeVentureId }),
    }
  )
);
