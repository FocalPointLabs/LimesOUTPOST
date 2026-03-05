// lib/hooks/index.ts
// All React Query hooks. Every hook that fetches venture-scoped data
// takes ventureId as the first argument and includes it in the query key.
// This guarantees React Query treats data for different ventures as
// completely separate cache entries — no stale data leaks on venture switch.

import {
  useQuery, useMutation, useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import {
  authApi, venturesApi, queueApi, pipelineApi, publishApi, analyticsApi,
} from "@/lib/api";
import { useVentureStore } from "@/store";
import type {
  Venture, QueueItem, QueuePatchRequest, PipelineRunRequest,
} from "@/types";

// ── Query key factory ─────────────────────────────────────────
// Centralised so invalidation is consistent across the app.
export const qk = {
  me:           ()                           => ["me"],
  ventures:     ()                           => ["ventures"],
  venture:      (id: string)                 => ["ventures", id],
  queue:        (vid: string, params?: object) => ["queue", vid, params],
  pipeline:     (vid: string, cid: number)   => ["pipeline", vid, cid],
  analytics:    (vid: string, platform?: string) => ["analytics", vid, platform],
};

// ── Auth ──────────────────────────────────────────────────────
export function useMe() {
  return useQuery({
    queryKey: qk.me(),
    queryFn:  () => authApi.me().then((r) => r.data),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

// ── Ventures ──────────────────────────────────────────────────
export function useVentures() {
  const setVentures = useVentureStore((s) => s.setVentures);

  return useQuery({
    queryKey: qk.ventures(),
    queryFn:  async () => {
      const data = await venturesApi.list().then((r) => r.data);
      setVentures(data); // keep Zustand in sync for the switcher
      return data;
    },
    staleTime: 30 * 1000,
  });
}

export function useVenture(id: string | null) {
  return useQuery({
    queryKey: qk.venture(id ?? ""),
    queryFn:  () => venturesApi.get(id!).then((r) => r.data),
    enabled:  !!id,
    staleTime: 30 * 1000,
  });
}

export function useCreateVenture() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: venturesApi.create,
    onSuccess:  () => qc.invalidateQueries({ queryKey: qk.ventures() }),
  });
}

export function usePatchVenture(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof venturesApi.patch>[1]) =>
      venturesApi.patch(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.venture(id) });
      qc.invalidateQueries({ queryKey: qk.ventures() });
    },
  });
}

// ── Queue ─────────────────────────────────────────────────────
export function useQueue(
  ventureId: string | null,
  params?: { platform?: string; status_filter?: string }
) {
  return useQuery({
    queryKey: qk.queue(ventureId ?? "", params),
    queryFn:  () => queueApi.list(ventureId!, params).then((r) => r.data),
    enabled:  !!ventureId,
    // Refetch every 30s so the queue stays fresh without manual refresh
    refetchInterval: 30 * 1000,
    staleTime: 10 * 1000,
  });
}

export function usePatchQueueItem(ventureId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, body }: { itemId: string; body: QueuePatchRequest }) =>
      queueApi.patch(ventureId, itemId, body).then((r) => r.data),
    // Optimistic update: immediately reflect the action in the UI
    onMutate: async ({ itemId, body }) => {
      await qc.cancelQueries({ queryKey: qk.queue(ventureId) });
      const prev = qc.getQueryData<QueueItem[]>(qk.queue(ventureId));

      qc.setQueryData<QueueItem[]>(qk.queue(ventureId), (old) =>
        old?.map((item) =>
          item.id === itemId
            ? {
                ...item,
                status:
                  body.action === "approve" ? "approved"
                  : body.action === "reject" ? "rejected"
                  : item.status,
              }
            : item
        )
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      // Roll back on error
      if (ctx?.prev) qc.setQueryData(qk.queue(ventureId), ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: qk.queue(ventureId) });
    },
  });
}

// ── Pipeline ──────────────────────────────────────────────────
export function usePipelineProgress(ventureId: string | null, campaignId: number | null) {
  return useQuery({
    queryKey: qk.pipeline(ventureId ?? "", campaignId ?? 0),
    queryFn:  () =>
      pipelineApi.progress(ventureId!, campaignId!).then((r) => r.data),
    enabled: !!ventureId && !!campaignId,
    refetchInterval: (query) => {
      // Stop polling once complete/failed
      const status = query.state.data?.overall;
      return status === "completed" || status === "failed" ? false : 3000;
    },
  });
}

export function useRunPipeline(ventureId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PipelineRunRequest) =>
      pipelineApi.run(ventureId, body).then((r) => r.data),
    onSuccess: () => {
      // Invalidate queue since a new run will eventually produce queue items
      qc.invalidateQueries({ queryKey: qk.queue(ventureId) });
    },
  });
}

export function useTriggerPublish(ventureId: string) {
  return useMutation({
    mutationFn: (platform: string) =>
      publishApi.trigger(ventureId, platform),
  });
}

// ── Analytics ─────────────────────────────────────────────────
export function useAnalytics(ventureId: string | null, platform = "youtube") {
  return useQuery({
    queryKey: qk.analytics(ventureId ?? "", platform),
    queryFn:  () => analyticsApi.summary(ventureId!, platform).then((r) => r.data),
    enabled:  !!ventureId,
    staleTime: 5 * 60 * 1000,
  });
}
