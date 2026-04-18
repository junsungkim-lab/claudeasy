import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { GitHubStatus, GitHubInstallation, GitHubRepo } from "@/api/client";

export function useGitHubStatus() {
  return useQuery<GitHubStatus>({
    queryKey: ["github", "status"],
    queryFn: () => api<GitHubStatus>("/api/github/status"),
    staleTime: 30_000,
  });
}

export function useInstallations(enabled = true) {
  return useQuery<GitHubInstallation[]>({
    queryKey: ["github", "installations"],
    queryFn: () => api<GitHubInstallation[]>("/api/github/installations"),
    enabled,
    staleTime: 60_000,
  });
}

export function useRepos(installationId: number | null) {
  return useQuery<GitHubRepo[]>({
    queryKey: ["github", "repos", installationId],
    queryFn: () => api<GitHubRepo[]>(`/api/github/installations/${installationId}/repos`),
    enabled: !!installationId,
    staleTime: 60_000,
  });
}
