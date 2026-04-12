import { useQuery } from "@tanstack/react-query";
import { api, type SessionInfo } from "@/api/client";

export function useSessions() {
  return useQuery<SessionInfo[]>({
    queryKey: ["sessions"],
    queryFn: () => api("/api/sessions"),
  });
}

export function useSessionContent(project: string | null, date: string | null) {
  return useQuery<{ content: string }>({
    queryKey: ["session-content", project, date],
    queryFn: () => api(`/api/sessions/${project}/${date}`),
    enabled: !!project && !!date,
  });
}
