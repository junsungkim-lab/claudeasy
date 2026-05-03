import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Loader2, CheckCircle2, AlertTriangle, LogIn, KeyRound, Package, Wifi } from "lucide-react";
import type { Card } from "@/api/client";

interface RuntimeGuidePayload {
  kind: "login_required" | "cred_missing" | "session_expired" | "dep_missing" | "port_conflict" | "unknown";
  message: string;
  detection: { type: string; target?: string };
  remediation_steps?: string[];
  auto_retry_parent?: boolean;
}

const KIND_CONFIG: Record<string, { icon: typeof LogIn; label: string; color: string }> = {
  login_required:  { icon: LogIn,        label: "로그인 필요",      color: "text-blue-600"  },
  session_expired: { icon: LogIn,        label: "세션 만료",        color: "text-amber-600" },
  cred_missing:    { icon: KeyRound,     label: "설정 값 필요",     color: "text-indigo-600"},
  dep_missing:     { icon: Package,      label: "패키지 설치 필요", color: "text-purple-600"},
  port_conflict:   { icon: Wifi,         label: "포트 충돌",        color: "text-red-600"   },
  unknown:         { icon: AlertTriangle,label: "오류 발생",        color: "text-gray-600"  },
};

export function RuntimeGuideCard({ card, boardId }: { card: Card; boardId: number }) {
  const qc = useQueryClient();

  const payload: RuntimeGuidePayload = (() => {
    try { return JSON.parse(card.output || "{}"); }
    catch { return { kind: "unknown", message: "알 수 없는 오류", detection: { type: "manual" } }; }
  })();

  const { mutate: resolve, isPending } = useMutation({
    mutationFn: () => api(`/api/cards/${card.id}/guide-resolve`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs", boardId] }),
  });

  if (card.status === "done") return null;

  const cfg = KIND_CONFIG[payload.kind] ?? KIND_CONFIG.unknown;
  const Icon = cfg.icon;
  const isAutoDetecting = payload.detection?.type !== "manual";
  const isError = card.status === "error";

  return (
    <div className="border border-amber-200 bg-amber-50 rounded-lg p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Icon size={14} className={cfg.color} />
        <span className="text-[13px] font-semibold text-amber-900">{cfg.label}</span>
      </div>

      <p className="text-[13px] text-amber-800 leading-relaxed">{payload.message}</p>

      {payload.remediation_steps && payload.remediation_steps.length > 0 && (
        <ol className="space-y-1 pl-1">
          {payload.remediation_steps.map((step, i) => (
            <li key={i} className="flex gap-2 text-[12px] text-amber-700">
              <span className="font-semibold shrink-0">{i + 1}.</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      )}

      {isAutoDetecting && !isError && (
        <div className="flex items-center gap-2 text-[11px] text-amber-600">
          <Loader2 size={11} className="animate-spin" />
          <span>완료되면 자동으로 감지됩니다…</span>
        </div>
      )}

      {(payload.detection?.type === "manual" || isError) && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => resolve()}
          disabled={isPending}
          className="w-full border-amber-300 text-amber-800 hover:bg-amber-100"
        >
          {isPending ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />}
          {isError ? "수동으로 완료 처리" : "완료했어요"}
        </Button>
      )}
    </div>
  );
}
