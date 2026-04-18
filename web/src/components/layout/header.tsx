import { useState } from "react";
import { Terminal, PanelLeft, GitBranch, Check, Loader2, ExternalLink, X } from "lucide-react";
import { useHealth } from "@/hooks/queries/use-health";
import { useGitHubStatus } from "@/hooks/queries/use-github";
import { useUIStore } from "@/stores/ui-store";
import { Tooltip } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { api } from "@/api/client";
import { cn } from "@/lib/utils";

function GitHubConnectModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<"idle" | "loading" | "code" | "done" | "error">("idle");
  const [info, setInfo] = useState<{ user_code: string; verification_uri: string; device_code: string; interval: number } | null>(null);
  const [error, setError] = useState("");
  const { refetch } = useGitHubStatus();

  const start = async () => {
    setStep("loading");
    try {
      const data = await api<any>("/api/github/auth/start", { method: "POST" });
      if (data.error) throw new Error(data.error);
      setInfo(data);
      setStep("code");
      poll(data.device_code, data.interval);
    } catch (e: any) {
      setError(e.message);
      setStep("error");
    }
  };

  const poll = async (device_code: string, interval: number) => {
    const deadline = Date.now() + 900_000;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, interval * 1000));
      try {
        const res = await api<any>("/api/github/auth/poll", {
          method: "POST",
          body: JSON.stringify({ device_code, interval }),
        });
        if (res.ok) {
          setStep("done");
          refetch();
          setTimeout(onClose, 1500);
          return;
        }
      } catch {}
    }
    setError("시간 초과되었습니다.");
    setStep("error");
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl p-5 w-[340px] space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-gray-900">GitHub 연결</span>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700"><X size={15} /></button>
        </div>

        {step === "idle" && (
          <>
            <p className="text-xs text-gray-500 leading-relaxed">
              GitHub 계정을 연결하면 작업 결과가 자동으로 repo에 저장됩니다.
            </p>
            <Button size="sm" className="w-full" onClick={start}>
              <GitBranch size={13} /> GitHub 연결 시작
            </Button>
          </>
        )}

        {step === "loading" && (
          <div className="flex items-center justify-center py-4 gap-2 text-sm text-gray-500">
            <Loader2 size={16} className="animate-spin" /> 준비 중...
          </div>
        )}

        {step === "code" && info && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500">아래 코드를 복사해 GitHub에서 입력하세요.</p>
            <div className="flex items-center justify-between bg-gray-100 rounded-lg px-4 py-3">
              <span className="text-lg font-mono font-bold tracking-widest text-gray-900">
                {info.user_code}
              </span>
              <button
                onClick={() => navigator.clipboard.writeText(info.user_code)}
                className="text-[10px] text-indigo-600 hover:text-indigo-700"
              >
                복사
              </button>
            </div>
            <a
              href={info.verification_uri}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-1.5 w-full py-2 text-xs text-white bg-gray-900 rounded-lg hover:bg-gray-800 transition-colors"
            >
              <ExternalLink size={12} /> github.com/login/device 에서 입력
            </a>
            <div className="flex items-center gap-1.5 text-[11px] text-gray-400">
              <Loader2 size={11} className="animate-spin" /> 승인 대기 중...
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="flex items-center justify-center gap-2 py-4 text-emerald-600">
            <Check size={18} /> <span className="text-sm font-medium">연결 완료!</span>
          </div>
        )}

        {step === "error" && (
          <div className="space-y-3">
            <p className="text-xs text-red-500">{error}</p>
            <Button size="sm" variant="outline" className="w-full" onClick={() => setStep("idle")}>
              다시 시도
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

export function Header() {
  const { data: health } = useHealth();
  const { data: ghStatus, refetch: refetchGH } = useGitHubStatus();
  const { toggleSidebar, openTrending } = useUIStore();
  const [showGHModal, setShowGHModal] = useState(false);

  const statusColor =
    !health
      ? "bg-gray-400"
      : health.claude_cli && health.claude_authed
      ? "bg-emerald-500"
      : health.claude_cli
      ? "bg-amber-400"
      : "bg-red-500";

  const statusText = !health
    ? "서버 연결 중..."
    : !health.claude_cli
    ? "Claude CLI 미설치"
    : !health.claude_authed
    ? `Claude CLI ${health.version ?? ""} (인증 필요)`
    : `Claude CLI ${health.version ?? ""} — 정상`;

  const handleDisconnect = async () => {
    await api("/api/github/auth", { method: "DELETE" });
    refetchGH();
  };

  return (
    <>
      <header className="h-11 flex items-center justify-between px-4 border-b border-gray-200 bg-white shrink-0">
        <div className="flex items-center gap-2">
          <button
            onClick={toggleSidebar}
            className="p-1 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100 transition-colors"
          >
            <PanelLeft size={16} />
          </button>
          <div className="flex items-center gap-1.5">
            <Terminal size={15} className="text-indigo-400" />
            <span className="text-sm font-semibold text-gray-900">claude-local</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={openTrending}
            className="text-xs text-gray-500 hover:text-gray-900 transition-colors"
          >
            GitHub Trending
          </button>

          {/* GitHub 연결 상태 */}
          {ghStatus?.connected ? (
            <Tooltip content={`${ghStatus.user?.login} — 클릭하여 연결 해제`}>
              <button
                onClick={handleDisconnect}
                className="flex items-center gap-1.5 text-xs text-emerald-600 hover:text-red-500 transition-colors"
              >
                <GitBranch size={12} />
                <span>{ghStatus.user?.login}</span>
              </button>
            </Tooltip>
          ) : (
            <button
              onClick={() => setShowGHModal(true)}
              className={cn(
                "flex items-center gap-1.5 text-xs transition-colors",
                ghStatus?.configured
                  ? "text-gray-500 hover:text-gray-900"
                  : "text-gray-300 cursor-not-allowed"
              )}
              disabled={!ghStatus?.configured}
              title={!ghStatus?.configured ? "GITHUB_CLIENT_ID 미설정" : undefined}
            >
              <GitBranch size={12} />
              GitHub 연결
            </button>
          )}

          <Tooltip content={statusText}>
            <div className="flex items-center gap-1.5 cursor-default">
              <div className={cn("w-2 h-2 rounded-full", statusColor)} />
              <span className="text-xs text-gray-500">
                {!health ? "연결 중" : health.claude_cli ? "정상" : "오류"}
              </span>
            </div>
          </Tooltip>
        </div>
      </header>

      {showGHModal && <GitHubConnectModal onClose={() => setShowGHModal(false)} />}
    </>
  );
}
