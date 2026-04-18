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
  ExternalLink,
  Clock,
  Pause,
  Play,
} from "lucide-react";
import { useBoards, useDeleteBoard } from "@/hooks/queries/use-boards";
import { useProjects } from "@/hooks/queries/use-projects";
import { useAgents, useSyncAgents } from "@/hooks/queries/use-agents";
import { useSessions } from "@/hooks/queries/use-sessions";
import { useScheduledBoards, usePauseSchedule, useResumeSchedule } from "@/hooks/queries/use-schedule";
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
    <aside className="w-56 shrink-0 border-r border-gray-200 bg-white flex flex-col overflow-hidden">
      {/* Project selector */}
      <div className="p-3 border-b border-gray-200">
        <div className="flex items-center justify-between mb-2 px-1">
          <span className="text-[10px] font-medium text-gray-500 uppercase tracking-wider">
            Project
          </span>
          <button
            onClick={() => refetchProjects()}
            className="text-gray-500 hover:text-gray-900 transition-colors"
            title="Refresh projects"
          >
            <RefreshCw size={10} className={fetchingProjects ? "animate-spin" : ""} />
          </button>
        </div>
        <button
          onClick={() => setSelectedProject(null)}
          className={cn(
            "w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-[12px] transition-colors",
            !selectedProjectPath
              ? "bg-gray-100 text-gray-900"
              : "text-gray-500 hover:bg-gray-100 hover:text-gray-900"
          )}
        >
          <FolderOpen size={12} />
          <span className="truncate">Global</span>
        </button>
        {projects.map((p: ProjectInfo) => (
          <button
            key={p.path}
            onClick={() => setSelectedProject(p.path)}
            className={cn(
              "w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-[12px] transition-colors",
              selectedProjectPath === p.path
                ? "bg-gray-100 text-gray-900"
                : "text-gray-500 hover:bg-gray-100 hover:text-gray-900"
            )}
          >
            <FolderOpen size={12} />
            <span className="truncate">{p.name}</span>
          </button>
        ))}
      </div>

      {/* Section tabs */}
      <div className="flex border-b border-gray-200 px-1 py-1 gap-0.5">
        {(["boards", "library", "history"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setSidebarSection(s)}
            className={cn(
              "flex-1 py-1.5 text-[10px] font-medium rounded-sm transition-colors flex items-center justify-center",
              sidebarSection === s
                ? "bg-gray-100 text-gray-900"
                : "text-gray-500 hover:text-gray-900"
            )}
            title={s === "boards" ? "Boards" : s === "library" ? "Library" : "History"}
          >
            {s === "boards" ? (
              <LayoutGrid size={11} />
            ) : s === "library" ? (
              <BookOpen size={11} />
            ) : (
              <History size={11} />
            )}
          </button>
        ))}
      </div>

      {/* Section content */}
      <div className="flex-1 overflow-y-auto">
        {sidebarSection === "boards" && (
          <>
            <BoardsSection
              boards={filteredBoards}
              selectedBoardId={selectedBoardId}
              onSelect={setSelectedBoard}
              onDelete={deleteBoard}
            />
            <ScheduledSection />
          </>
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
        <p className="text-[11px] text-gray-500 text-center py-6">
          보드가 없습니다
        </p>
      )}
      {boards.map((b) => (
        <div
          key={b.id}
          className={cn(
            "flex items-start gap-2 px-2 py-2 rounded-md transition-colors group",
            selectedBoardId === b.id
              ? "bg-indigo-600/15 border border-indigo-500/30 text-gray-900"
              : "text-gray-500 hover:bg-gray-100 border border-transparent"
          )}
        >
          <button
            className="flex items-start gap-2 flex-1 min-w-0 text-left"
            onClick={() => {
              window.location.href = `/board/${b.id}`;
            }}
          >
            <StatusDot status={b.status} />
            <div className="min-w-0 flex-1 mt-0.5">
              <p className="text-[12px] truncate leading-4 font-medium">{b.name}</p>
              <p className="text-[10px] text-gray-500 mt-0.5">
                <StatusLabel status={b.status} />
              </p>
            </div>
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              window.open(`/board/${b.id}`, "_blank");
            }}
            className="opacity-0 group-hover:opacity-100 transition-opacity mt-0.5 shrink-0 text-gray-500 hover:text-gray-900"
            title="Open in new tab"
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
      : "bg-gray-400";

  return <div className={cn("w-1.5 h-1.5 rounded-full mt-1.5 shrink-0", color)} />;
}

function StatusLabel({ status }: { status: string }) {
  const map: Record<string, string> = {
    generating: "생성 중",
    ready: "준비됨",
    running: "실행 중",
    done: "완료",
    error: "오류",
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
          <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-500" />
          <Input
            className="pl-6 h-7 text-xs bg-gray-100 border-gray-200"
            placeholder="Search..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Button
          size="icon"
          variant="ghost"
          onClick={() => sync()}
          disabled={isPending}
          title="Sync"
        >
          <RefreshCw size={12} className={isPending ? "animate-spin" : ""} />
        </Button>
      </div>
      {isLoading ? (
        <p className="text-[11px] text-gray-500 text-center py-4">로딩 중...</p>
      ) : (
        <div className="space-y-0.5">
          {agents.map((a) => (
            <div
              key={a.name}
              className="px-2 py-1.5 rounded-md hover:bg-gray-100 group transition-colors"
            >
              <div className="flex items-center gap-1.5">
                <span className="text-[12px] font-medium text-gray-900 truncate">
                  {a.name}
                </span>
                {a.source === "global" ? (
                  <Badge variant="secondary" className="text-[9px] px-1 py-0">
                    custom
                  </Badge>
                ) : (
                  <Badge variant="default" className="text-[9px] px-1 py-0">
                    H
                  </Badge>
                )}
              </div>
              <p className="text-[11px] text-gray-500 truncate mt-0.5">
                {a.description}
              </p>
            </div>
          ))}
          {agents.length === 0 && (
            <p className="text-[11px] text-gray-500 text-center py-4">
              에이전트 없음
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function ScheduledSection() {
  const { data: scheduled = [] } = useScheduledBoards();
  const { mutate: pause } = usePauseSchedule();
  const { mutate: resume } = useResumeSchedule();

  if (scheduled.length === 0) return null;

  return (
    <div className="px-2 pb-2 border-t border-gray-100 mt-1 pt-2">
      <div className="flex items-center gap-1.5 px-1 mb-1.5">
        <Clock size={10} className="text-gray-400" />
        <span className="text-[10px] font-medium text-gray-400 uppercase tracking-wider">
          스케줄됨
        </span>
      </div>
      <div className="space-y-0.5">
        {scheduled.map((b) => (
          <div
            key={b.id}
            className="flex items-center gap-1.5 px-2 py-1.5 rounded-md hover:bg-gray-100 group transition-colors"
          >
            <button
              className="flex-1 min-w-0 text-left"
              onClick={() => { window.location.href = `/board/${b.id}`; }}
            >
              <p className={cn(
                "text-[12px] truncate font-medium leading-4",
                b.paused ? "text-gray-400" : "text-gray-800"
              )}>
                {b.name}
              </p>
              <div className="flex items-center gap-1 mt-0.5">
                <span className="text-[9px] font-mono text-gray-400 bg-gray-100 px-1 py-0.5 rounded">
                  {b.cron_expr}
                </span>
                {b.next_run_at && !b.paused && (
                  <span className="text-[9px] text-gray-400 truncate">
                    {formatNextRun(b.next_run_at)}
                  </span>
                )}
                {b.paused && (
                  <span className="text-[9px] text-amber-500">일시정지</span>
                )}
              </div>
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (b.paused) resume(b.id);
                else pause(b.id);
              }}
              className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 text-gray-400 hover:text-gray-700"
              title={b.paused ? "재개" : "일시정지"}
            >
              {b.paused ? <Play size={11} /> : <Pause size={11} />}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatNextRun(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = d.getTime() - now.getTime();
  const diffH = Math.floor(diffMs / 3_600_000);
  const diffM = Math.floor((diffMs % 3_600_000) / 60_000);
  if (diffMs < 0) return "곧";
  if (diffH === 0) return `${diffM}분 후`;
  if (diffH < 24) return `${diffH}시간 후`;
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const isToday = d.getDate() === now.getDate();
  const isTomorrow = d.getDate() === tomorrow.getDate();
  const hhmm = d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
  if (isToday) return `오늘 ${hhmm}`;
  if (isTomorrow) return `내일 ${hhmm}`;
  return `${d.getMonth() + 1}/${d.getDate()} ${hhmm}`;
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
      <p className="text-[11px] text-gray-500 text-center py-6 px-2">
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
            className="w-full flex items-center gap-1.5 px-1 py-1 text-[11px] font-medium text-gray-500 hover:text-gray-900 transition-colors"
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
                  className="text-[10px] px-1.5 py-0.5 rounded-sm bg-gray-100 text-gray-500 hover:bg-gray-200 hover:text-gray-900 transition-colors"
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
