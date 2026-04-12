import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Star, GitFork, Loader2, ExternalLink, Zap, Download } from "lucide-react";
import { api } from "@/api/client";
import { useTrending, useApplyTrending } from "@/hooks/queries/use-trending";
import { useTrendingWs } from "@/hooks/sockets/use-trending-ws";
import { useUIStore } from "@/stores/ui-store";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import type { TrendingRepo } from "@/api/client";

export function TrendingModal() {
  const { trendingOpen, closeTrending, selectedProjectPath } = useUIStore();
  const [language, setLanguage] = useState("");
  const [since, setSince] = useState("daily");
  const [analyzeId, setAnalyzeId] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState<string | null>(null); // owner/repo
  const [analysisResults, setAnalysisResults] = useState<Record<string, string>>({});
  const { mutate: applyTrending, isPending: applying } = useApplyTrending();

  const { data: repos = [], isLoading, error } = useTrending(language, since, trendingOpen);
  const { output, done } = useTrendingWs(analyzeId);

  // When analysis finishes, store result
  const currentAnalyzing = analyzing;
  if (done && analyzeId && currentAnalyzing && output && !analysisResults[currentAnalyzing]) {
    setAnalysisResults((prev) => ({ ...prev, [currentAnalyzing]: output }));
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

  const handleApply = (repoKey: string) => {
    const analysis = analysisResults[repoKey];
    if (!analysis) return;
    applyTrending({ analysis, project_path: selectedProjectPath }, {
      onSuccess: closeTrending,
    });
  };

  return (
    <Dialog
      open={trendingOpen}
      onClose={closeTrending}
      title="GitHub Trending"
      className="max-w-2xl max-h-[80vh] flex flex-col"
    >
      <div className="flex flex-col overflow-hidden">
        {/* Filters */}
        <div className="flex gap-2 p-4 border-b border-[--color-border]">
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
        </div>

        {/* List */}
        <div className="overflow-y-auto flex-1 p-4 space-y-3" style={{ maxHeight: "60vh" }}>
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={20} className="animate-spin text-[--color-muted-foreground]" />
            </div>
          )}
          {error && (
            <p className="text-sm text-red-400 text-center py-8">로드 실패: 잠시 후 다시 시도하세요</p>
          )}
          {repos.map((repo) => {
            const key = repo.full_name;
            const isAnalyzing = analyzing === key;
            const analysisOutput = isAnalyzing ? output : analysisResults[key];
            const isDone = !isAnalyzing && !!analysisResults[key];

            return (
              <div
                key={key}
                className="border border-[--color-border] rounded-lg p-3 bg-[--color-card] space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-[--color-foreground]">
                        {repo.full_name}
                      </span>
                      {repo.language && (
                        <Badge variant="secondary" className="text-[10px]">{repo.language}</Badge>
                      )}
                    </div>
                    {repo.description && (
                      <p className="text-xs text-[--color-muted-foreground] mt-0.5 line-clamp-2">
                        {repo.description}
                      </p>
                    )}
                    <div className="flex items-center gap-3 mt-1.5">
                      <span className="flex items-center gap-1 text-[10px] text-amber-400">
                        <Star size={10} /> {repo.stars.toLocaleString()}
                      </span>
                      {repo.stars_period > 0 && (
                        <span className="text-[10px] text-[--color-muted-foreground]">
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
                      className="inline-flex items-center justify-center h-7 w-7 rounded-md border border-[--color-border] text-[--color-muted-foreground] hover:text-[--color-foreground] hover:bg-[--color-accent] transition-colors"
                    >
                      <ExternalLink size={12} />
                    </a>
                  </div>
                </div>

                {analysisOutput && (
                  <div className="border-t border-[--color-border] pt-2 space-y-2">
                    <div className="prose-output bg-[--color-background] rounded-md p-2.5 border border-[--color-border] max-h-48 overflow-y-auto text-xs">
                      <ReactMarkdown>{analysisOutput}</ReactMarkdown>
                    </div>
                    {isDone && (
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={() => handleApply(key)}
                          disabled={applying}
                          className="text-xs"
                        >
                          {applying ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
                          {selectedProjectPath ? "내 프로젝트에 적용" : "보드로 만들기"}
                        </Button>
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
  );
}
