import { useQuery } from "@tanstack/react-query";
import { api, type HealthStatus } from "@/api/client";

export function useHealth() {
  return useQuery<HealthStatus>({
    queryKey: ["health"],
    queryFn: () => api("/health"),
    refetchInterval: 30_000,
    retry: false,
  });
}
