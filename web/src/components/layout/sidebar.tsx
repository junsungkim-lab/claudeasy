import { useState } from "react";
import {
  LayoutGrid,
  BookOpen,
  History,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  Search,
  RefreshCw,
  Plus,
  Check,
  ExternalLink,
} from "lucide-react";
import { useBoards, useDeleteBoard } from "@/hooks/queries/use-boards";
import { useProjects } from "@/hooks/queries/use-projects";
import { useAgents, useSyncAgents } from "@/hooks/queries/use-agents";
import { useSessions } from "@/hooks/queries/use-sessions";
import { useUIStore } from "@/stores/ui-store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ProjectInfo } from "@/api/client";

export function Sidebar() {
  const {
    selectedProjectPath,
    selectedBoardId,
    sidebarSection,
    setSidebarSection,
    setSelectedProject,
    setSelectedBoard,
    openHistoryDrawer,
  } = useUIStore();

  const { data: boards = [] } = useBoards();
  const { data: projects = [], refetch: refetchProjects, isFetching: fetchingProjects } = useProjects();
  const { mutate: deleteBoard } = useDeleteBoard();

  const filteredBoards = selectedProjectPath
    ? boards.filter((b) => b.project_path === selectedProjectPath)
    : boards.filter((b) => !b.project_path);


  return (
    <aside className="w-56 shrink-0 border-r border-[--color-border] bg-[#111118] flex flex-col overflow-hidden">
      {/* Project selector */}
      <div className="p-2 border-b border-[--color-border]">
        <div className="flex items-center justify-between mb-1.5 px-1">
          <span className="text-[10px] font-medium text-[--color-muted-foreground] uppercase tracking-wider">Project</span>
          <button
            onClick={() => refetchProjects()}
            className="text-[--color-muted-foreground] hover:text-[--color-foreground] transition-colors"
            title="프로젝트 목록 새로고침"
          >
            <RefreshCw size={10} className={fetchingProjects ? "animate-spin" : ""} />
          </button>
        </div>
        <button
          onClick={() => setSelectedProject(null)}
          className={cn(
            "w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-sm transition-colors",
            !selectedProjectPath
              ? "bg-[--color-accent] text-[--color-foreground]"
              : "text-[--color-muted-foreground] hover:bg-[--color-accent] hover:text-[--color-foreground]"
          )}
        >
          <FolderOpen size={13} />
          <span className="truncate">Global</span>
          {!selectedProjectPath && <Check size={12} className="ml-auto shrink-0" />}
        </button>
        {projects.map((p: ProjectInfo) => (
          <button
            key={p.path}
            onClick={() => setSelectedProject(p.path)}
            className={cn(
              "w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-sm transition-colors",
              selectedProjectPath === p.path
                ? "bg-[--color-accent] text-[--color-foreground]"
                : "text-[--color-muted-foreground] hover:bg-[--color-accent] hover:text-[--color-foreground]"
            )}
          >
            <FolderOpen size={13} />
            <span className="truncate">{p.name}</span>
            {selectedProjectPath === p.path && <Check size={12} className="ml-auto shrink-0" />}
          </button>
        ))}
      </div>

      {/* Section tabs */}
      <div className="flex border-b border-[--color-border]">
        {(["boards", "library", "history"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setSidebarSection(s)}
            className={cn(
              "flex-1 py-2 text-[10px] font-medium uppercase tracking-wider transition-colors",
              sidebarSection === s
                ? "text-[--color-foreground] border-b-2 border-[--color-primary]"
                : "text-[--color-muted-foreground] hover:text-[--color-foreground]"
            )}
          >
            {s === "boards" ? <LayoutGrid size={12} className="mx-auto" /> :
             s === "library" ? <BookOpen size={12} className="mx-auto" /> :
             <History size={12} className="mx-auto" />}
          </button>
        ))}
      </div>

      {/* Section content */}
      <div className="flex-1 overflow-y-auto">
        {sidebarSection === "boards" && (
          <BoardsSection
            boards={filteredBoards}
            selectedBoardId={selectedBoardId}
            onSelect={setSelectedBoard}
            onDelete={deleteBoard}
          />
        )}
        {sidebarSection === "library" && <LibrarySection />}
        {sidebarSection === "history" && (
          <HistorySection onOpen={openHistoryDrawer} />
        )}
      </div>
    </aside>
  );
}

function BoardsSection({
  boards,
  selectedBoardId,
  onSelect,
  onDelete,
}: {
  boards: any[];
  selectedBoardId: number | null;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  return (
    <div className="p-2 space-y-0.5">
      {boards.length === 0 && (
        <p className="text-[11px] text-[--color-muted-foreground] text-center py-6">
          보드가 없습니다
        </p>
      )}
      {boards.map((b) => (
        <div
          key={b.id}
          className={cn(
            "flex items-start gap-2 px-2 py-2 rounded-md transition-colors group",
            selectedBoardId === b.id
              ? "bg-indigo-600/20 text-[--color-foreground]"
              : "text-[--color-muted-foreground] hover:bg-[--color-accent] hover:text-[--color-foreground]"
          )}
        >
          <button className="flex items-start gap-2 flex-1 min-w-0 text-left" onClick={() => { window.location.href = `/board/${b.id}`; }}>
            <StatusDot status={b.status} />
            <div className="min-w-0 flex-1 mt-0.5">
              <p className="text-xs truncate leading-4">{b.name}</p>
              <p className="text-[10px] text-[--color-muted-foreground] mt-0.5">
                <StatusLabel status={b.status} />
              </p>
            </div>
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); window.open(`/board/${b.id}`, "_blank"); }}
            className="opacity-0 group-hover:opacity-100 transition-opacity mt-0.5 shrink-0 hover:text-[--color-foreground]"
            title="새 탭으로 열기"
          >
            <ExternalLink size={11} />
          </button>
        </div>
      ))}
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "done"
      ? "bg-emerald-500"
      : status === "running"
      ? "bg-blue-500 animate-pulse"
      : status === "error"
      ? "bg-red-500"
      : status === "generating"
      ? "bg-amber-400 animate-pulse"
      : status === "ready"
      ? "bg-indigo-400"
      : "bg-zinc-500";

  return <div className={cn("w-1.5 h-1.5 rounded-full mt-1.5 shrink-0", color)} />;
}

function StatusLabel({ status }: { status: string }) {
  const map: Record<string, string> = {
    generating: "⟳ 생성 중...",
    ready: "● 준비됨",
    running: "▶ 실행 중...",
    done: "✓ 완료",
    error: "✕ 오류",
  };
  return <>{map[status] ?? status}</>;
}

function LibrarySection() {
  const [search, setSearch] = useState("");
  const { data: agents = [], isLoading } = useAgents(search);
  const { mutate: sync, isPending } = useSyncAgents();

  return (
    <div className="p-2">
      <div className="flex gap-1.5 mb-2">
        <div className="relative flex-1">
          <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-[--color-muted-foreground]" />
          <Input
            className="pl-6 h-7 text-xs"
            placeholder="검색..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Button
          size="icon"
          variant="ghost"
          onClick={() => sync()}
          disabled={isPending}
          title="동기화"
        >
          <RefreshCw size={12} className={isPending ? "animate-spin" : ""} />
        </Button>
      </div>
      {isLoading ? (
        <p className="text-[11px] text-[--color-muted-foreground] text-center py-4">로딩 중...</p>
      ) : (
        <div className="space-y-0.5">
          {agents.map((a) => (
            <div key={a.name} className="px-2 py-1.5 rounded-md hover:bg-[--color-accent] group">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-medium text-[--color-foreground] truncate">{a.name}</span>
                {a.harness && (
                  <Badge variant="default" className="text-[9px] px-1 py-0">H</Badge>
                )}
              </div>
              <p className="text-[11px] text-[--color-muted-foreground] truncate mt-0.5">
                {a.description}
              </p>
            </div>
          ))}
          {agents.length === 0 && (
            <p className="text-[11px] text-[--color-muted-foreground] text-center py-4">
              에이전트 없음
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function HistorySection({ onOpen }: { onOpen: (project: string, date: string) => void }) {
  const { data: sessions = [] } = useSessions();
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const toggle = (project: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(project)) next.delete(project);
      else next.add(project);
      return next;
    });
  };

  if (sessions.length === 0) {
    return (
      <p className="text-[11px] text-[--color-muted-foreground] text-center py-6 px-2">
        히스토리 없음
      </p>
    );
  }

  return (
    <div className="p-2 space-y-1">
      {sessions.map((s) => (
        <div key={s.project}>
          <button
            onClick={() => toggle(s.project)}
            className="w-full flex items-center gap-1.5 px-1 py-1 text-[11px] font-medium text-[--color-muted-foreground] hover:text-[--color-foreground] transition-colors"
          >
            {collapsed.has(s.project) ? (
              <ChevronRight size={11} />
            ) : (
              <ChevronDown size={11} />
            )}
            <span className="truncate">{s.project}</span>
          </button>
          {!collapsed.has(s.project) && (
            <div className="pl-4 flex flex-wrap gap-1 mb-1">
              {s.dates.map((d) => (
                <button
                  key={d}
                  onClick={() => onOpen(s.project, d)}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-[--color-muted] text-[--color-muted-foreground] hover:bg-[--color-accent] hover:text-[--color-foreground] transition-colors"
                >
                  {d.slice(5)}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
