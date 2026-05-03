import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Star, Loader2, ExternalLink, Zap, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { api } from "@/api/client";
import { useTrending, useApplyTrending } from "@/hooks/queries/use-trending";
import { useTrendingWs, type TrendingStructured } from "@/hooks/sockets/use-trending-ws";
import { useUIStore } from "@/stores/ui-store";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { TrendingRepo } from "@/api/client";

function VerdictBadge({ verdict, score, why }: TrendingStructured) {
  const config = {
    recommended: { icon: CheckCircle2, label: "추천", cls: "bg-emerald-50 border-emerald-200 text-emerald-700" },
    risky: { icon: AlertTriangle, label: "주의", cls: "bg-amber-50 border-amber-200 text-amber-700" },
    skip: { icon: XCircle, label: "패스", cls: "bg-gray-50 border-gray-200 text-gray-500" },
  };
  const c = config[verdict] ?? config.skip;
  const Icon = c.icon;
  const stars = "★".repeat(Math.min(score, 5)) + "☆".repeat(Math.max(0, 5 - score));

  return (
    <div className={cn("flex items-center gap-2 px-2.5 py-1.5 rounded-md border text-xs", c.cls)}>
      <Icon size={12} />
      <span className="font-semibold">{c.label}</span>
      <span className="font-mono text-[11px] tracking-tight">{stars}</span>
      {why && <span className="text-[11px] opacity-80 truncate max-w-[180px]">{why}</span>}
    </div>
  );
}

function ApplyConfirmDialog({
  open, onConfirm, onCancel, applying
}: {
  open: boolean;
  onConfirm: (autoRun: boolean) => void;
  onCancel: () => void;
  applying: boolean;
}) {
  const [autoRun, setAutoRun] = useState(false);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onCancel}>
      <div className="bg-white rounded-xl shadow-xl p-5 max-w-sm w-full mx-4" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-sm font-semibold text-gray-900 mb-2">분석 내용을 프로젝트에 적용할까요?</h3>
        <p className="text-xs text-gray-500 mb-4">
          외부 레포 코드를 적용합니다. 단계마다 확인받기가 기본으로 켜져 있어 각 카드를 직접 승인해야 진행됩니다.
        </p>
        <label className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer mb-4">
          <input
            type="checkbox"
            checked={autoRun}
            onChange={(e) => setAutoRun(e.target.checked)}
            className="rounded"
          />
          지금부터 자동 실행으로 바꾸기
        </label>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => onConfirm(autoRun)} disabled={applying} className="flex-1">
            {applying ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
            적용하기
          </Button>
          <Button size="sm" variant="ghost" onClick={onCancel}>취소</Button>
        </div>
      </div>
    </div>
  );
}

export function TrendingModal() {
  const { trendingOpen, closeTrending, selectedProjectPath } = useUIStore();
  const [language, setLanguage] = useState("");
  const [since, setSince] = useState("daily");
  const [analyzeId, setAnalyzeId] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [analysisResults, setAnalysisResults] = useState<Record<string, { output: string; structured: TrendingStructured | null }>>({});
  const [confirmRepo, setConfirmRepo] = useState<TrendingRepo | null>(null);
  const { mutate: applyTrending, isPending: applying } = useApplyTrending();

  const { data: repos = [], isLoading, error } = useTrending(language, since, trendingOpen);
  const { output, done, structured } = useTrendingWs(analyzeId);

  const currentAnalyzing = analyzing;
  if (done && analyzeId && currentAnalyzing && output && !analysisResults[currentAnalyzing]) {
    setAnalysisResults((prev) => ({ ...prev, [currentAnalyzing]: { output, structured: structured ?? null } }));
    setAnalyzeId(null);
    setAnalyzing(null);
  }

  const handleAnalyze = async (repo: TrendingRepo) => {
    const key = repo.full_name;
    setAnalyzing(key);
    setAnalyzeId(null);
    try {
      const result = await api<{ analyze_id: string }>("/api/trending/analyze", {
        method: "POST",
        body: JSON.stringify({
          owner: repo.owner,
          repo: repo.repo,
          project_path: selectedProjectPath,
        }),
      });
      setAnalyzeId(result.analyze_id);
    } catch {
      setAnalyzing(null);
    }
  };

  const handleApplyConfirm = (autoRun: boolean) => {
    if (!confirmRepo) return;
    const key = confirmRepo.full_name;
    const result = analysisResults[key];
    if (!result) return;
    applyTrending(
      {
        analysis: result.output,
        owner: confirmRepo.owner,
        repo: confirmRepo.repo,
        project_path: selectedProjectPath,
        approval_mode: autoRun ? "auto" : "manual",
      },
      { onSuccess: () => { closeTrending(); setConfirmRepo(null); } }
    );
  };

  // 분석 결과에서 VERDICT 첫 줄 제거해서 마크다운만 표시
  const cleanOutput = (raw: string) => {
    const lines = raw.split("\n");
    if (lines[0]?.startsWith("VERDICT:")) return lines.slice(1).join("\n").trimStart();
    return raw;
  };

  return (
    <>
      <Dialog
        open={trendingOpen}
        onClose={closeTrending}
        title="GitHub Trending"
        className="max-w-2xl max-h-[80vh] flex flex-col"
      >
        <div className="flex flex-col overflow-hidden">
          <div className="flex gap-2 p-4 border-b border-gray-200">
            <Select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-36"
            >
              <option value="">All Languages</option>
              <option value="python">Python</option>
              <option value="typescript">TypeScript</option>
              <option value="javascript">JavaScript</option>
              <option value="go">Go</option>
              <option value="rust">Rust</option>
              <option value="swift">Swift</option>
              <option value="kotlin">Kotlin</option>
              <option value="java">Java</option>
            </Select>
            <Select
              value={since}
              onChange={(e) => setSince(e.target.value)}
              className="w-28"
            >
              <option value="daily">오늘</option>
              <option value="weekly">이번 주</option>
              <option value="monthly">이번 달</option>
            </Select>
            {selectedProjectPath && (
              <span className="ml-auto flex items-center text-[10px] text-indigo-500 font-mono truncate max-w-[200px]">
                {selectedProjectPath.split("/").slice(-2).join("/")} 기준
              </span>
            )}
          </div>

          <div className="overflow-y-auto flex-1 p-4 space-y-3" style={{ maxHeight: "60vh" }}>
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <Loader2 size={20} className="animate-spin text-gray-500" />
              </div>
            )}
            {error && (
              <p className="text-sm text-red-400 text-center py-8">로드 실패: 잠시 후 다시 시도하세요</p>
            )}
            {repos.map((repo) => {
              const key = repo.full_name;
              const isAnalyzing = analyzing === key;
              const result = isAnalyzing ? { output, structured: structured ?? null } : analysisResults[key];
              const isDone = !isAnalyzing && !!analysisResults[key];
              const canApply = isDone && (result?.structured?.verdict !== "skip");

              return (
                <div key={key} className="border border-gray-200 rounded-lg p-3 bg-white space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-gray-900">{repo.full_name}</span>
                        {repo.language && (
                          <Badge variant="secondary" className="text-[10px]">{repo.language}</Badge>
                        )}
                      </div>
                      {repo.description && (
                        <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{repo.description}</p>
                      )}
                      <div className="flex items-center gap-3 mt-1.5">
                        <span className="flex items-center gap-1 text-[10px] text-amber-400">
                          <Star size={10} /> {repo.stars.toLocaleString()}
                        </span>
                        {repo.stars_period > 0 && (
                          <span className="text-[10px] text-gray-500">
                            +{repo.stars_period} {since === "daily" ? "오늘" : since === "weekly" ? "이번 주" : "이번 달"}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex gap-1.5 shrink-0">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleAnalyze(repo)}
                        disabled={isAnalyzing || !!analyzing}
                      >
                        {isAnalyzing ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
                        {isAnalyzing ? "분석 중..." : "분석"}
                      </Button>
                      <a
                        href={repo.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center justify-center h-7 w-7 rounded-md border border-gray-200 text-gray-500 hover:text-gray-900 hover:bg-gray-100 transition-colors"
                      >
                        <ExternalLink size={12} />
                      </a>
                    </div>
                  </div>

                  {result?.output && (
                    <div className="border-t border-gray-200 pt-2 space-y-2">
                      {result.structured && (
                        <VerdictBadge {...result.structured} />
                      )}
                      <div className="prose-output bg-gray-50 rounded-md p-2.5 border border-gray-200 max-h-48 overflow-y-auto text-xs">
                        <ReactMarkdown>{cleanOutput(result.output)}</ReactMarkdown>
                      </div>
                      {isDone && (
                        <div className="flex items-center gap-2">
                          {canApply ? (
                            <Button
                              size="sm"
                              onClick={() => setConfirmRepo(repo)}
                              disabled={applying}
                              className="text-xs"
                            >
                              <Zap size={11} />
                              이 프로젝트에 적용
                            </Button>
                          ) : (
                            <span className="text-[10px] text-gray-400">이 레포는 적용하지 않는 것을 권장해요</span>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </Dialog>

      <ApplyConfirmDialog
        open={!!confirmRepo}
        onConfirm={handleApplyConfirm}
        onCancel={() => setConfirmRepo(null)}
        applying={applying}
      />
    </>
  );
}
