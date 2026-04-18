import { Clock, Trash2, GitBranch } from "lucide-react";
import { useDeleteBoard } from "@/hooks/queries/use-boards";
import { useUIStore } from "@/stores/ui-store";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { RunSelector } from "./run-selector";
import { cn, projectName } from "@/lib/utils";
import type { Board } from "@/api/client";

export function BoardHeader({ board }: { board: Board }) {
  const { openScheduleModal, setSelectedBoard } = useUIStore();
  const { mutate: deleteBoard } = useDeleteBoard();

  const handleDelete = () => {
    if (confirm(`"${board.name}" 보드를 삭제하시겠습니까?`)) {
      deleteBoard(board.id, {
        onSuccess: () => setSelectedBoard(null),
      });
    }
  };

  return (
    <div className="border-b border-gray-200 bg-white px-5 py-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="min-w-0">
          <h1 className="text-[15px] font-semibold text-gray-900 truncate">
            {board.name}
          </h1>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {board.github_repo && (
            <a
              href={`https://github.com/${board.github_repo}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-sm bg-gray-100 text-gray-500 hover:text-gray-900 transition-colors font-mono"
            >
              <GitBranch size={9} />
              {board.github_repo}
            </a>
          )}
          {board.cron_expr && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-sm bg-gray-100 text-gray-500 font-mono">
              {board.cron_expr}
            </span>
          )}
          {board.project_path && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-sm bg-gray-100 text-gray-500">
              {projectName(board.project_path)}
            </span>
          )}
          <Button
            size="icon"
            variant="ghost"
            className="text-gray-500 hover:text-gray-900 h-7 w-7"
            onClick={() => openScheduleModal(board.id)}
            title="Schedule"
          >
            <Clock size={13} />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="text-gray-500 hover:text-red-400 h-7 w-7"
            onClick={handleDelete}
            title="Delete"
          >
            <Trash2 size={13} />
          </Button>
        </div>
      </div>

      <div>
        <RunSelector boardId={board.id} />
      </div>
    </div>
  );
}
