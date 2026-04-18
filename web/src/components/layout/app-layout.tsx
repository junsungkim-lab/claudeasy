import { Header } from "./header";
import { Sidebar } from "./sidebar";
import { NewBoardForm } from "@/components/board/new-board-form";
import { TrendingModal } from "@/components/modals/trending-modal";
import { ScheduleModal } from "@/components/modals/schedule-modal";
import { ProjectGateModal } from "@/components/modals/project-gate-modal";
import { HistoryDrawer } from "@/components/history/history-panel";
import { useUIStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

export function AppLayout() {
  const { sidebarCollapsed } = useUIStore();

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <div
          className={cn(
            "transition-all duration-200 overflow-hidden",
            sidebarCollapsed ? "w-0" : "w-56"
          )}
        >
          {!sidebarCollapsed && <Sidebar />}
        </div>
        <main className="flex-1 flex items-center justify-center p-8">
          <div className="w-full max-w-lg space-y-4">
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
        </main>
      </div>

      <HistoryDrawer />
      <TrendingModal />
      <ScheduleModal />
      <ProjectGateModal />
    </div>
  );
}
