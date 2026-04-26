import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type AutomationInfo } from "@/api/client";

export function useAutomation(boardId: number | null) {
  return useQuery<AutomationInfo>({
    queryKey: ["automation", boardId],
    queryFn: () => api(`/api/boards/${boardId}/automation`),
    enabled: !!boardId,
    staleTime: 10_000,
  });
}

export function useSaveBoardEnv(boardId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, string>) =>
      api(`/api/boards/${boardId}/env`, {
        method: "POST",
        body: JSON.stringify(values),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["automation", boardId] });
    },
  });
}
