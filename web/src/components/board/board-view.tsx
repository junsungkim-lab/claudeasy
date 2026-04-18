import { useBoards } from "@/hooks/queries/use-boards";
import { useRuns, useRunCards } from "@/hooks/queries/use-runs";
import { useBoardWs } from "@/hooks/sockets/use-board-ws";
import { useRunWs } from "@/hooks/sockets/use-run-ws";
import { useUIStore } from "@/stores/ui-store";
import { BoardHeader } from "./board-header";
import { CardColumns } from "@/components/card/card-column";
import { ActivityLog } from "./activity-log";
import { NewBoardForm } from "./new-board-form";
import { useEffect } from "react";

export function BoardView() {
  const { selectedBoardId, selectedRunId, setSelectedRun } = useUIStore();
  const { data: boards = [] } = useBoards();
  const board = boards.find((b) => b.id === selectedBoardId) ?? null;

  const { data: runs = [] } = useRuns(selectedBoardId);
  const latestRun = runs[0] ?? null;
  const activeRunId = selectedRunId ?? latestRun?.id ?? null;

  // Auto-select latest run
  useEffect(() => {
    if (!selectedRunId && latestRun) {
      setSelectedRun(latestRun.id);
    }
  }, [latestRun?.id, selectedRunId, setSelectedRun]);

  const cards = useRunCards(selectedBoardId, activeRunId);

  // WebSocket subscriptions
  const { events, statusText } = useBoardWs(selectedBoardId);
  useRunWs(activeRunId, selectedBoardId);

  const isGenerating =
    board?.status === "generating" ||
    latestRun?.status === "generating" ||
    events.length > 0;  // WS 이벤트가 있으면 무조건 생성 중으로 간주

  const hasCards = cards.length > 0;

  // 보드 없음 → 빈 화면 + 새 보드 폼
  if (!board) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <div className="w-full max-w-lg space-y-6">
            <div className="text-center">
              <h2 className="text-base font-semibold text-gray-900 mb-1">
                새 자동화 만들기
              </h2>
              <p className="text-xs text-gray-500">
                좌측에서 보드를 선택하거나 아래에서 새 작업을 만드세요
              </p>
            </div>
            <NewBoardForm />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <BoardHeader board={board} />

      <div className="flex-1 overflow-hidden">
        {/* 생성 중이고 카드가 아직 없으면 Activity Log */}
        {isGenerating && !hasCards ? (
          <ActivityLog
            statusText={statusText}
            events={events}
            boardStatus={board.status}
          />
        ) : hasCards ? (
          /* 카드 있으면 칸반 */
          <CardColumns cards={cards} />
        ) : (
          /* 대기 중 (ready but no cards) */
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-gray-500">카드 없음</p>
          </div>
        )}
      </div>

      {/* 하단 새 보드 폼 */}
      <div className="p-4 border-t border-gray-200 bg-gray-50">
        <NewBoardForm />
      </div>
    </div>
  );
}
