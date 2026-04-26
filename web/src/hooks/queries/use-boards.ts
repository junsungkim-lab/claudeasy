import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Board } from "@/api/client";

export function useBoards() {
  return useQuery<Board[]>({
    queryKey: ["boards"],
    queryFn: () => api("/api/boards"),
    staleTime: 0,          // 항상 최신 상태 유지
    refetchInterval: 5000, // 5초마다 폴링 (WS 없을 때 fallback)
  });
}

export function useCreateBoard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      request: string;
      approval_mode?: string;
      project_path?: string | null;
    }) =>
      api<any>("/api/boards", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      // 서버는 {board_id, run_id, ...board} 형태로 반환
      const newBoard: Board = { ...data, id: data.board_id ?? data.id };
      // 캐시에 즉시 추가 → selectedBoard 설정 직후 바로 보드를 찾을 수 있게
      qc.setQueryData(["boards"], (old: Board[] = []) => [newBoard, ...old]);
      qc.invalidateQueries({ queryKey: ["boards"] });
    },
  });
}

export function useDeleteBoard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ boardId, deleteFiles = false }: { boardId: number; deleteFiles?: boolean }) =>
      api(`/api/boards/${boardId}?delete_files=${deleteFiles}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["boards"] }),
  });
}

export function useSetBoardProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ boardId, projectPath }: { boardId: number; projectPath: string | null }) =>
      api(`/api/boards/${boardId}/set-project`, {
        method: "POST",
        body: JSON.stringify({ project_path: projectPath }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["boards"] }),
  });
}
