#!/bin/bash
# claude-local 실행 스크립트
# 사용법:
#   ./dev.sh          → 8100 포트 (일반 사용)
#   ./dev.sh --dev    → 5173 포트 (프론트엔드 개발 시)

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# icu4c 심볼릭 링크 (node 호환성)
for lib in /opt/homebrew/Cellar/icu4c/74.2/lib/libicu*.74.dylib; do
  [ -e "$lib" ] || continue
  name=$(basename "$lib")
  target="/opt/homebrew/opt/icu4c/lib/$name"
  [ -e "$target" ] || ln -sf "$lib" "$target" 2>/dev/null || true
done

cleanup() {
  echo ""
  echo "종료 중..."
  kill 0 2>/dev/null
  exit 0
}
trap cleanup SIGINT SIGTERM

# 포트 정리
kill_port() { lsof -ti :"$1" 2>/dev/null | xargs kill -9 2>/dev/null || true; }
kill_port 8100

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  claude-local"

if [[ "$1" == "--dev" ]]; then
  # 개발 모드: Vite dev server (5173) + FastAPI (8100)
  kill_port 5173
  echo "  접속 → http://localhost:5173  [개발 모드]"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  cd "$ROOT" && python3 server.py &
  sleep 1
  cd "$ROOT/web" && bun --bun vite --port 5173 &
else
  # 일반 모드: FastAPI만 (빌드된 React 서빙)
  echo "  접속 → http://localhost:8100"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  cd "$ROOT" && python3 server.py &
fi

echo "  Ctrl+C 로 종료"
echo ""
wait
