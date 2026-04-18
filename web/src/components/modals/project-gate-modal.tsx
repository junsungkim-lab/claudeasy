import { useState } from "react";
import { FolderOpen, Plus } from "lucide-react";
import { useProjects, useCreateProject } from "@/hooks/queries/use-projects";
import { useSetBoardProject } from "@/hooks/queries/use-boards";
import { useUIStore } from "@/stores/ui-store";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ProjectInfo } from "@/api/client";

export function ProjectGateModal() {
  const { projectGate, closeProjectGate } = useUIStore();
  const { data: projects = [] } = useProjects();
  const { mutate: createProject, isPending: creating } = useCreateProject();
  const { mutate: setProject } = useSetBoardProject();

  const [newPath, setNewPath] = useState("");
  const [showNew, setShowNew] = useState(false);

  const handleSelectProject = (path: string) => {
    if (!projectGate) return;
    setProject({ boardId: projectGate.boardId, projectPath: path });
    closeProjectGate();
  };

  const handleCreateProject = () => {
    if (!newPath.trim() || !projectGate) return;
    createProject(newPath.trim(), {
      onSuccess: () => {
        setProject({ boardId: projectGate.boardId, projectPath: newPath.trim() });
        closeProjectGate();
        setNewPath("");
        setShowNew(false);
      },
    });
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
          코드 생성을 위해 프로젝트 경로가 필요합니다.
        </p>

        {projects.length > 0 && (
          <div className="space-y-1">
            {projects.map((p: ProjectInfo) => (
              <button
                key={p.path}
                onClick={() => handleSelectProject(p.path)}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-left border border-gray-200 hover:bg-gray-100 transition-colors"
              >
                <FolderOpen size={13} className="text-gray-500" />
                <span className="text-xs text-gray-900 truncate">{p.name}</span>
              </button>
            ))}
          </div>
        )}

        {showNew ? (
          <div className="space-y-2">
            <Input
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              placeholder="/Users/username/my-project"
              onKeyDown={(e) => e.key === "Enter" && handleCreateProject()}
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={handleCreateProject} disabled={creating || !newPath.trim()} className="flex-1">
                {creating ? "추가 중..." : "추가"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowNew(false)}>취소</Button>
            </div>
          </div>
        ) : (
          <Button size="sm" variant="outline" className="w-full" onClick={() => setShowNew(true)}>
            <Plus size={13} />
            새 프로젝트 경로 추가
          </Button>
        )}
      </div>
    </Dialog>
  );
}
