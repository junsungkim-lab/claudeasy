import ReactMarkdown from "react-markdown";
import { Loader2 } from "lucide-react";
import { useSessionContent } from "@/hooks/queries/use-sessions";
import { useUIStore } from "@/stores/ui-store";
import { Drawer } from "@/components/ui/drawer";

export function HistoryDrawer() {
  const {
    historyDrawerOpen,
    selectedHistoryProject,
    selectedHistoryDate,
    closeHistoryDrawer,
  } = useUIStore();

  const { data, isLoading, error } = useSessionContent(
    selectedHistoryProject,
    selectedHistoryDate
  );

  const title = selectedHistoryProject && selectedHistoryDate
    ? `${selectedHistoryProject} · ${selectedHistoryDate}`
    : "히스토리";

  return (
    <Drawer open={historyDrawerOpen} onClose={closeHistoryDrawer} title={title} className="w-[600px]">
      <div className="p-4">
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={18} className="animate-spin text-[--color-muted-foreground]" />
          </div>
        )}
        {error && (
          <p className="text-sm text-red-400 text-center py-8">히스토리를 불러올 수 없습니다</p>
        )}
        {data?.content && (
          <div className="prose-output">
            <ReactMarkdown>{data.content}</ReactMarkdown>
          </div>
        )}
      </div>
    </Drawer>
  );
}
