# claude-local (claudeasy) 플랫폼 개발 지침

## 프로젝트 정체성

**claude-local = claudeasy SaaS 플랫폼** — 비개발자 고객이 AI 자동화 보드를 만들고 실행하는 서비스.

핵심 파일:
- `server.py` — FastAPI 백엔드, 카드 실행, WS, 스케줄러
- `harness.py` — 하네스 생성 LLM, 카드 실행 에이전트, 진단/가이드 로직
- `db.py` — SQLite 데이터 레이어
- `web/` — React 19 프런트엔드

## ⚠️ 절대 규칙: 플랫폼 레벨에서만 고친다

**보드 안의 생성된 프로젝트 파일(예: `claudeasy-projects/19-seo/naver_uploader.py`)은 직접 수정하지 않는다.**

무언가 잘못됐을 때 올바른 접근:

| 증상 | 잘못된 대응 | 올바른 대응 |
|------|------------|------------|
| 생성된 코드가 Playwright 사용 | `naver_uploader.py` 직접 수정 | `harness.py` 시스템 프롬프트 규칙 추가 |
| 패키지 누락으로 카드 실패 | 해당 프로젝트 `requirements.txt` 수정 | `server.py` `_extract_missing_package` + 자동 pip install |
| 로그인 만료로 카드 실패 | 쿠키 파일 직접 삭제·재생성 | `harness.py` `diagnose_failure` + P5 runtime guide 카드 |
| .env 값 누락 | .env 직접 편집 | `audit_runtime_prereqs` 개선 + env_input 카드 |

**19-seo, 기타 `claudeasy-projects/` 하위 디렉터리는 테스트 케이스일 뿐이다.** 거기서 발견한 문제는 플랫폼을 고쳐서 해결한다. 플랫폼이 올바르면 다음번 생성 시 자동으로 올바른 코드가 나온다.

## 플랫폼 레이어별 책임

### harness.py — 코드 생성 품질
- `HARNESS_SYSTEM_PROJECT` / `HARNESS_SYSTEM_GLOBAL`: 보드 생성 시 에이전트에게 전달되는 시스템 프롬프트
- `HARNESS_TOOL_DEV_SYSTEM`: 도구 개발 에이전트용 시스템 프롬프트
- 규칙 추가 위치: 이 프롬프트들의 `## ⚠️ CRITICAL` 섹션
- `diagnose_failure()` / `audit_runtime_prereqs()`: 런타임 실패 LLM 진단

### server.py — 런타임 자동화
- `_try_diagnose_and_guide()`: 카드 실패 시 자동 진단 → runtime_guide 카드 생성
- `_spawn_detection_watcher()`: 조건 충족 감지 → 부모 카드 자동 재실행
- `_maybe_audit_board()`: 보드 첫 진입 시 프리플라이트 점검
- `_extract_missing_package()`: ImportError → pip install 자동화

### db.py — 데이터
- `create_runtime_guide_card()`: 가이드 카드 DB 생성

### web/ — UI
- `runtime-guide-card.tsx`: 가이드 카드 렌더링 컴포넌트
- `card-drawer.tsx`: 카드 종류별 컨텐츠 분기

## 현재 구현된 핵심 기능 (P5 런타임 멘토)

1. **실패 자동 진단**: 카드 rc≠0 → LLM이 stderr 분석 → `kind`(login_required/cred_missing/dep_missing 등) 분류
2. **runtime_guide 카드 자동 생성**: 비개발자용 한국어 안내 + 단계별 가이드
3. **조건 감지 watcher**: cookie_file / file_watch / url_probe / http_probe / manual 5종
4. **자동 재실행**: 조건 충족 시 부모 카드 자동 재실행 (사용자 개입 불필요)
5. **dep_missing 자동 처리**: `pip install` 자동 실행 후 카드 재실행
6. **보드 audit**: 첫 진입 시 `.env.example` vs `.env` 누락 키 감지

## 하네스 시스템 프롬프트 핵심 규칙 (현재)

- **규칙 4**: Anthropic SDK 금지 → Claude CLI subprocess만 허용
- **규칙 5**: 크리덴셜은 반드시 `.env.example` → env_input 카드로 수집
- **규칙 6**: 외부 인증은 `ensure_logged_in()` 패턴 (headed browser 자동 오픈)
- **규칙 7**: 공식 REST API 우선; Playwright는 API 없을 때만 최후 수단
- **OAuth 패턴**: 로컬 HTTP 콜백 서버 방식 — 사용자에게 URL 복사 요구 금지
