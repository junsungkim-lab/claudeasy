import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UIState {
  // Project selection
  selectedProjectPath: string | null;
  // Board/run selection
  selectedBoardId: number | null;
  selectedRunId: number | null;
  // Card drawer
  activeCardId: number | null;
  // Sidebar
  sidebarSection: "boards" | "library" | "history";
  sidebarCollapsed: boolean;
  // Modals
  trendingOpen: boolean;
  scheduleModalBoardId: number | null;
  projectGate: { boardId: number } | null;
  // History
  selectedHistoryProject: string | null;
  selectedHistoryDate: string | null;
  historyDrawerOpen: boolean;
}

interface UIActions {
  setSelectedProject: (path: string | null) => void;
  setSelectedBoard: (id: number | null) => void;
  setSelectedRun: (id: number | null) => void;
  setActiveCard: (id: number | null) => void;
  setSidebarSection: (s: UIState["sidebarSection"]) => void;
  toggleSidebar: () => void;
  openTrending: () => void;
  closeTrending: () => void;
  openScheduleModal: (boardId: number) => void;
  closeScheduleModal: () => void;
  openProjectGate: (boardId: number) => void;
  closeProjectGate: () => void;
  openHistoryDrawer: (project: string, date: string) => void;
  closeHistoryDrawer: () => void;
}

export const useUIStore = create<UIState & UIActions>()(
  persist(
    (set) => ({
      selectedProjectPath: null,
      selectedBoardId: null,
      selectedRunId: null,
      activeCardId: null,
      sidebarSection: "boards",
      sidebarCollapsed: false,
      trendingOpen: false,
      scheduleModalBoardId: null,
      projectGate: null,
      selectedHistoryProject: null,
      selectedHistoryDate: null,
      historyDrawerOpen: false,

      setSelectedProject: (path) =>
        set({ selectedProjectPath: path, selectedBoardId: null, selectedRunId: null }),
      setSelectedBoard: (id) => {
        window.history.pushState(null, "", id ? `/board/${id}` : "/");
        set({ selectedBoardId: id, selectedRunId: null, activeCardId: null });
      },
      setSelectedRun: (id) => set({ selectedRunId: id, activeCardId: null }),
      setActiveCard: (id) => set({ activeCardId: id }),
      setSidebarSection: (s) => set({ sidebarSection: s }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      openTrending: () => set({ trendingOpen: true }),
      closeTrending: () => set({ trendingOpen: false }),
      openScheduleModal: (boardId) => set({ scheduleModalBoardId: boardId }),
      closeScheduleModal: () => set({ scheduleModalBoardId: null }),
      openProjectGate: (boardId) => set({ projectGate: { boardId } }),
      closeProjectGate: () => set({ projectGate: null }),
      openHistoryDrawer: (project, date) =>
        set({ selectedHistoryProject: project, selectedHistoryDate: date, historyDrawerOpen: true }),
      closeHistoryDrawer: () => set({ historyDrawerOpen: false }),
    }),
    {
      name: "claude-local-ui",
      partialize: (s) => ({
        selectedProjectPath: s.selectedProjectPath,
        sidebarCollapsed: s.sidebarCollapsed,
        sidebarSection: s.sidebarSection,
      }),
    }
  )
);
