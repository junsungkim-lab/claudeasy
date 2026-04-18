import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";

export interface ScheduledBoard {
  id: number;
  name: string;
  cron_expr: string;
  status: string;
  next_run_at: string | null;
  paused: boolean;
}

export function useScheduledBoards() {
  return useQuery<ScheduledBoard[]>({
    queryKey: ["boards-scheduled"],
    queryFn: () => api("/api/boards/scheduled"),
    refetchInterval: 30_000,
  });
}

export function usePauseSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (boardId: number) =>
      api(`/api/boards/${boardId}/schedule/pause`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["boards-scheduled"] });
    },
  });
}

export function useResumeSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (boardId: number) =>
      api(`/api/boards/${boardId}/schedule/resume`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["boards-scheduled"] });
    },
  });
}

interface ScheduleInfo {
  cron_expr: string | null;
  approval_mode: "auto" | "manual";
  status: string;
}

export function useSchedule(boardId: number | null) {
  return useQuery<ScheduleInfo>({
    queryKey: ["schedule", boardId],
    queryFn: () => api(`/api/boards/${boardId}/schedule`),
    enabled: !!boardId,
  });
}

export function useSetSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      boardId,
      cron_expr,
      approval_mode,
    }: {
      boardId: number;
      cron_expr: string;
      approval_mode: "auto" | "manual";
    }) =>
      api(`/api/boards/${boardId}/schedule`, {
        method: "PUT",
        body: JSON.stringify({ cron_expr, approval_mode }),
      }),
    onSuccess: (_, { boardId }) => {
      qc.invalidateQueries({ queryKey: ["schedule", boardId] });
      qc.invalidateQueries({ queryKey: ["boards"] });
    },
  });
}

export function useDeleteSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (boardId: number) =>
      api(`/api/boards/${boardId}/schedule`, { method: "DELETE" }),
    onSuccess: (_, boardId) => {
      qc.invalidateQueries({ queryKey: ["schedule", boardId] });
      qc.invalidateQueries({ queryKey: ["boards"] });
    },
  });
}

export function useTriggerSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (boardId: number) =>
      api(`/api/boards/${boardId}/schedule/trigger`, { method: "POST" }),
    onSuccess: (_, boardId) => {
      qc.invalidateQueries({ queryKey: ["runs", boardId] });
    },
  });
}
