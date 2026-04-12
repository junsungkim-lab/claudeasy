import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type TrendingRepo } from "@/api/client";

export function useTrending(language: string, since: string, enabled: boolean) {
  return useQuery<TrendingRepo[]>({
    queryKey: ["trending", language, since],
    queryFn: () =>
      api(
        `/api/trending?language=${encodeURIComponent(language)}&since=${since}`
      ),
    enabled,
    staleTime: 5 * 60_000, // 5 min
  });
}

export function useTrendingClones() {
  return useQuery<{ name: string; path: string; size_mb: number }[]>({
    queryKey: ["trending-clones"],
    queryFn: () => api("/api/trending/clones"),
  });
}

export function useDeleteClone() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ owner, repo }: { owner: string; repo: string }) =>
      api(`/api/trending/clones/${owner}/${repo}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["trending-clones"] }),
  });
}

export function useApplyTrending() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      analysis,
      project_path,
    }: {
      analysis: string;
      project_path: string | null;
    }) =>
      api("/api/trending/apply", {
        method: "POST",
        body: JSON.stringify({ analysis, project_path }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["boards"] }),
  });
}
