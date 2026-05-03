import { useBoards } from "@/hooks/queries/use-boards";
import { useRuns, useRunCards } from "@/hooks/queries/use-runs";
import { useBoardWs } from "@/hooks/sockets/use-board-ws";
import { useRunWs } from "@/hooks/sockets/use-run-ws";
import { useUIStore } from "@/stores/ui-store";
import { BoardHeader } from "./board-header";
import { CardColumns } from "@/components/card/card-column";
import { ActivityLog } from "./activity-log";
import { NewBoardForm } from "./new-board-form";
import { MessageCircle } from "lucide-react";
import { useEffect, useMemo } from "react";

export function BoardView() {
  const { selectedBoardId, selectedRunId, setSelectedRun, setActiveCard } = useUIStore();
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

  // 미답변 agent_reply가 있는 카드 맵
  const pendingRepliesMap = useMemo(() => {
    const map: Record<number, number> = {};
    for (const c of cards) {
      if ((c as any).pending_replies > 0) {
        map[c.id] = (c as any).pending_replies;
      }
    }
    return map;
  }, [cards]);

  const firstPendingCard = cards.find((c) => (pendingRepliesMap[c.id] ?? 0) > 0) ?? null;

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
        {/* 미답변 agent_reply 배너 */}
        {firstPendingCard && (
          <button
            onClick={() => setActiveCard(firstPendingCard.id)}
            className="mx-4 mt-3 flex items-center gap-2 px-3 py-2 rounded-md bg-amber-50 border border-amber-200 text-xs text-amber-700 hover:bg-amber-100 transition-colors w-auto"
          >
            <MessageCircle size={13} className="text-amber-500" />
            <span><strong>{firstPendingCard.title}</strong> 카드에서 답변을 기다리고 있어요 — 클릭해서 답변하기</span>
          </button>
        )}

        {/* 생성 중이고 카드가 아직 없으면 Activity Log */}
        {isGenerating && !hasCards ? (
          <ActivityLog
            statusText={statusText}
            events={events}
            boardStatus={board.status}
          />
        ) : hasCards ? (
          /* 카드 있으면 칸반 */
          <CardColumns cards={cards} pendingRepliesMap={pendingRepliesMap} />
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
