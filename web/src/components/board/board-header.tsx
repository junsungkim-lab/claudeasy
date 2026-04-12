import { Clock, Trash2, ChevronDown } from "lucide-react";
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
    <div className="border-b border-[--color-border] bg-[--color-card] px-5 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-sm font-semibold text-[--color-foreground] truncate">
              {board.name}
            </h1>
            {board.project_path && (
              <Badge variant="secondary" className="text-[10px]">
                {projectName(board.project_path)}
              </Badge>
            )}
            {board.cron_expr && (
              <Badge variant="default" className="text-[10px]">
                <Clock size={9} className="mr-0.5" />
                {board.cron_expr}
              </Badge>
            )}
          </div>
          {board.description && board.description.trim() !== board.name.trim() && (
            <p className="text-xs text-[--color-muted-foreground] mt-0.5 truncate">
              {board.description}
            </p>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            size="icon"
            variant="ghost"
            onClick={() => openScheduleModal(board.id)}
            title="스케줄 설정"
          >
            <Clock size={14} />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            onClick={handleDelete}
            title="보드 삭제"
            className="text-[--color-muted-foreground] hover:text-red-400"
          >
            <Trash2 size={14} />
          </Button>
        </div>
      </div>

      <div className="mt-2">
        <RunSelector boardId={board.id} />
      </div>
    </div>
  );
}
