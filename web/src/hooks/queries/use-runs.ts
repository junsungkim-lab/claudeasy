import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Run, type Card } from "@/api/client";

interface RunWithCards extends Run {
  cards: Card[];
}

export function useRuns(boardId: number | null) {
  return useQuery<RunWithCards[]>({
    queryKey: ["runs", boardId],
    queryFn: () => api(`/api/boards/${boardId}/runs`),
    enabled: !!boardId,
    staleTime: 0,
  });
}

export function useCards(runId: number | null) {
  // Cards are embedded in runs response — select from there
  // This hook is a convenience wrapper that queries runs and extracts cards
  return useQuery<Card[]>({
    queryKey: ["cards", runId],
    queryFn: async () => {
      // No dedicated endpoint — return empty, cards come from run WS updates
      // The board view reads cards from useRuns() directly
      return [];
    },
    enabled: false, // disabled — use useRunCards instead
  });
}

export function useRunCards(boardId: number | null, runId: number | null) {
  const { data: runs = [] } = useRuns(boardId);
  const run = runs.find((r) => r.id === runId) ?? runs[0];
  return run?.cards ?? [];
}

export function useRerun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (boardId: number) =>
      api<Run>(`/api/boards/${boardId}/runs`, { method: "POST" }),
    onSuccess: (_, boardId) => {
      qc.invalidateQueries({ queryKey: ["runs", boardId] });
      qc.invalidateQueries({ queryKey: ["boards"] });
    },
  });
}

export function useDeleteRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ boardId, runId }: { boardId: number; runId: number }) =>
      api(`/api/boards/${boardId}/runs/${runId}`, { method: "DELETE" }),
    onSuccess: (_, { boardId }) => {
      qc.invalidateQueries({ queryKey: ["runs", boardId] });
    },
  });
}
