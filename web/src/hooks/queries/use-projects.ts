import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ProjectInfo } from "@/api/client";

export function useProjects() {
  return useQuery<ProjectInfo[]>({
    queryKey: ["projects"],
    queryFn: () => api("/api/projects"),
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (path: string) =>
      api("/api/projects/create", {
        method: "POST",
        body: JSON.stringify({ path }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}
