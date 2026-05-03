import { useState } from "react";
import { FolderOpen, Plus, ChevronDown, ChevronUp } from "lucide-react";
import { useProjects } from "@/hooks/queries/use-projects";
import { useSetBoardProject } from "@/hooks/queries/use-boards";
import { useUIStore } from "@/stores/ui-store";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/api/client";
import type { ProjectInfo } from "@/api/client";

export function ProjectGateModal() {
  const { projectGate, closeProjectGate } = useUIStore();
  const { data: projects = [] } = useProjects();
  const { mutate: setProject } = useSetBoardProject();

  const [newName, setNewName] = useState("");
  const [showNameInput, setShowNameInput] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advancedPath, setAdvancedPath] = useState("");
  const [creating, setCreating] = useState(false);

  const handleSelectProject = (path: string) => {
    if (!projectGate) return;
    setProject({ boardId: projectGate.boardId, projectPath: path });
    closeProjectGate();
  };

  const handleCreateByName = async () => {
    if (!newName.trim() || !projectGate) return;
    setCreating(true);
    try {
      const res = await api("/api/projects/create", {
        method: "POST",
        body: JSON.stringify({ name: newName.trim() }),
      }) as { path: string };
      setProject({ boardId: projectGate.boardId, projectPath: res.path });
      closeProjectGate();
      setNewName("");
      setShowNameInput(false);
    } finally {
      setCreating(false);
    }
  };

  const handleAdvancedPath = async () => {
    if (!advancedPath.trim() || !projectGate) return;
    setCreating(true);
    try {
      await api("/api/projects/create", {
        method: "POST",
        body: JSON.stringify({ path: advancedPath.trim() }),
      });
      setProject({ boardId: projectGate.boardId, projectPath: advancedPath.trim() });
      closeProjectGate();
      setAdvancedPath("");
      setShowAdvanced(false);
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog
      open={!!projectGate}
      onClose={closeProjectGate}
      title="프로젝트 선택"
      className="max-w-sm"
    >
      <div className="p-4 space-y-3">
        <p className="text-xs text-gray-500">
          작업할 프로젝트를 선택하거나 새로 만들어 주세요.
        </p>

        {projects.length > 0 && (
          <div className="space-y-1">
            <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide">최근 프로젝트</p>
            {projects.slice(0, 5).map((p: ProjectInfo) => (
              <button
                key={p.path}
                onClick={() => handleSelectProject(p.path)}
                className="w-full flex items-center gap-2 px-3 py-2.5 rounded-md text-left border border-gray-200 hover:bg-indigo-50 hover:border-indigo-200 transition-colors"
              >
                <FolderOpen size={14} className="text-indigo-400 shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-medium text-gray-900 truncate">{p.name}</p>
                  {p.has_git && (
                    <p className="text-[10px] text-gray-400">git 프로젝트</p>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}

        {showNameInput ? (
          <div className="space-y-2">
            <p className="text-[10px] text-gray-500">프로젝트 이름을 입력하면 ~/Documents/ 안에 폴더를 만들어 드립니다.</p>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="예: 날씨-알림-봇"
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleCreateByName()}
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={handleCreateByName} disabled={creating || !newName.trim()} className="flex-1">
                {creating ? "만드는 중..." : "새 프로젝트 만들기"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowNameInput(false)}>취소</Button>
            </div>
          </div>
        ) : (
          <Button size="sm" variant="outline" className="w-full" onClick={() => setShowNameInput(true)}>
            <Plus size={13} />
            새 프로젝트 만들기
          </Button>
        )}

        <button
          className="w-full flex items-center justify-between text-[10px] text-gray-400 hover:text-gray-600 transition-colors pt-1"
          onClick={() => setShowAdvanced(!showAdvanced)}
        >
          <span>고급: 직접 경로 입력</span>
          {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
        {showAdvanced && (
          <div className="space-y-2">
            <Input
              value={advancedPath}
              onChange={(e) => setAdvancedPath(e.target.value)}
              placeholder="/Users/username/my-project"
              onKeyDown={(e) => e.key === "Enter" && handleAdvancedPath()}
            />
            <Button size="sm" onClick={handleAdvancedPath} disabled={creating || !advancedPath.trim()} className="w-full">
              {creating ? "추가 중..." : "이 경로 사용"}
            </Button>
          </div>
        )}
      </div>
    </Dialog>
  );
}
