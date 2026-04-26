import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useBoards } from "@/hooks/queries/use-boards";
import { useRuns, useRunCards } from "@/hooks/queries/use-runs";
import { useBoardWs } from "@/hooks/sockets/use-board-ws";
import { useRunWs } from "@/hooks/sockets/use-run-ws";
import { useUIStore } from "@/stores/ui-store";
import { BoardHeader } from "./board-header";
import { CardColumns } from "@/components/card/card-column";
import { ActivityLog } from "./activity-log";
import { CardDrawer } from "@/components/card/card-drawer";
import { BoardOutputView } from "./board-output-view";

interface BoardPageProps {
  boardId: number;
}

export function BoardPage({ boardId }: BoardPageProps) {
  const { setSelectedRun, selectedRunId } = useUIStore();
  const [view, setView] = useState<"board" | "output">(
    window.location.hash === "#output" ? "output" : "board"
  );

  useEffect(() => {
    const onHashChange = () => setView(window.location.hash === "#output" ? "output" : "board");
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  // CardDrawer가 selectedBoardId/selectedRunId 기반으로 카드를 찾으므로 store에 세팅
  useEffect(() => {
    useUIStore.setState({ selectedBoardId: boardId });
    return () => { useUIStore.setState({ selectedBoardId: null, selectedRunId: null }); };
  }, [boardId]);

  const { data: boards = [] } = useBoards();
  const board = boards.find((b) => b.id === boardId) ?? null;

  const { data: runs = [] } = useRuns(boardId);
  const latestRun = runs[0] ?? null;
  const activeRunId = selectedRunId ?? latestRun?.id ?? null;

  useEffect(() => {
    if (!selectedRunId && latestRun) setSelectedRun(latestRun.id);
  }, [latestRun?.id, selectedRunId, setSelectedRun]);

  const cards = useRunCards(boardId, activeRunId);
  const { events, statusText } = useBoardWs(boardId);
  useRunWs(activeRunId, boardId);

  const isGenerating =
    board?.status === "generating" ||
    latestRun?.status === "generating" ||
    events.length > 0;

  const hasCards = cards.length > 0;

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* 뒤로가기 바 */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-200 bg-white shrink-0">
        <button
          onClick={() => history.back()}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 transition-colors"
        >
          <ArrowLeft size={14} />
          뒤로
        </button>
        {board && (
          <span className="text-xs text-gray-500 truncate max-w-xs">
            {board.name}
          </span>
        )}
      </div>

      {/* 보드 헤더 (run selector, 재실행 등) */}
      {board && <BoardHeader board={board} onOutputView={() => setView("output")} showOutputButton={view !== "output"} />}

      {/* 메인 콘텐츠 */}
      <div className="flex-1 overflow-hidden">
        {!board ? (
          <div className="flex items-center justify-center h-full text-sm text-gray-500">
            보드를 불러오는 중...
          </div>
        ) : view === "output" ? (
          <BoardOutputView boardId={boardId} />
        ) : isGenerating && !hasCards ? (
          <ActivityLog statusText={statusText} events={events} boardStatus={board.status} />
        ) : hasCards ? (
          <CardColumns cards={cards} />
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-gray-500">
            카드 없음
          </div>
        )}
      </div>

      {view !== "output" && <CardDrawer />}
    </div>
  );
}
