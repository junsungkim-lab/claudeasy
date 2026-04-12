import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Agent } from "@/api/client";

export function useAgents(search = "") {
  return useQuery<Agent[]>({
    queryKey: ["agents", search],
    queryFn: () => api(`/api/agents${search ? `?q=${encodeURIComponent(search)}` : ""}`),
  });
}

export function useSyncAgents() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/api/agents/sync", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}
