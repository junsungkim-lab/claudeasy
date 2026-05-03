import { useState, useRef } from "react";
import { SendHorizonal, Loader2, Lock, Unlock } from "lucide-react";
import { useCreateBoard } from "@/hooks/queries/use-boards";
import { useUIStore } from "@/stores/ui-store";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function NewBoardForm() {
  const [request, setRequest] = useState("");
  const [approvalMode, setApprovalMode] = useState<"auto" | "manual">("auto");
  const { selectedProjectPath } = useUIStore();
  const { mutate: createBoard, isPending } = useCreateBoard();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    if (!request.trim() || isPending) return;
    createBoard(
      {
        request: request.trim(),
        approval_mode: approvalMode,
        project_path: selectedProjectPath,
      },
      {
        onSuccess: (board) => {
          const id = (board as any).board_id ?? (board as any).id;
          window.location.href = `/board/${id}`;
        },
        onError: (err) => {
          alert(`오류: ${err.message}`);
        },
      }
    );
  };

  return (
    <div className="border border-gray-200 rounded-xl bg-white p-3 shadow-sm">
      <textarea
        ref={textareaRef}
        value={request}
        onChange={(e) => setRequest(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit();
        }}
        placeholder="무엇을 만들거나 자동화하고 싶으신가요? (Cmd+Enter로 제출)"
        className="w-full bg-transparent text-sm text-gray-900 placeholder:text-gray-500 resize-none outline-none min-h-[60px] leading-relaxed"
        rows={3}
        disabled={isPending}
      />
      <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-200">
        <div className="flex flex-col gap-0.5">
          <button
            onClick={() => setApprovalMode(approvalMode === "auto" ? "manual" : "auto")}
            className={cn(
              "flex items-center gap-1.5 text-xs transition-colors",
              approvalMode === "manual"
                ? "text-amber-500"
                : "text-gray-500 hover:text-gray-900"
            )}
          >
            {approvalMode === "manual" ? <Lock size={12} /> : <Unlock size={12} />}
            {approvalMode === "manual" ? "단계마다 확인받기" : "바로 만들고 보여주기"}
          </button>
          {approvalMode === "manual" && (
            <p className="text-[10px] text-amber-400 pl-4">
              카드가 완성될 때마다 승인 버튼을 눌러야 진행됩니다.
            </p>
          )}
        </div>

        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={!request.trim() || isPending}
        >
          {isPending ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <SendHorizonal size={13} />
          )}
          {isPending ? "생성 중..." : "실행"}
        </Button>
      </div>
    </div>
  );
}
