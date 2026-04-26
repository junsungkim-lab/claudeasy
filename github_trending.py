"""
GitHub 트렌딩 탐색 + 레포 클론 + 요약

github.com/trending 페이지 직접 스크래핑 (공식 API 없음).
since=daily|weekly|monthly, language 필터 지원.

클론 위치: ~/Documents/github-trending/{owner}__{repo}/
"""
from __future__ import annotations

import asyncio
import re
import shutil
import time
from pathlib import Path

import httpx

HOME = Path.home()
CLONE_BASE = HOME / "Documents" / "github-trending"
TRENDING_URL = "https://github.com/trending"
CACHE_TTL = 1800  # 30분

_trending_cache = {}  # cache_key -> (timestamp, data)


async def search_trending(
    language: str = "",
    since: str = "daily",
    limit: int = 25,
) -> list:
    """
    github.com/trending 스크래핑.
    since: daily | weekly | monthly
    language: python, typescript, javascript, go, rust, swift, ... (빈 문자열 = 전체)
    """
    cache_key = f"{language}_{since}"
    if cache_key in _trending_cache:
        ts, data = _trending_cache[cache_key]
        if time.time() - ts < CACHE_TTL:
            return data[:limit]

    url = TRENDING_URL
    params = {"since": since}
    if language:
        url = f"{TRENDING_URL}/{language.lower()}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        html = r.text

    result = _parse_trending_html(html)
    _trending_cache[cache_key] = (time.time(), result)
    return result[:limit]


def _parse_trending_html(html: str) -> list:
    """github.com/trending HTML에서 레포 목록 파싱."""
    repos = []

    articles = re.findall(
        r'<article[^>]*class="[^"]*Box-row[^"]*"[^>]*>(.*?)</article>',
        html, re.DOTALL
    )

    for article in articles:
        try:
            # owner/repo — h2 > a 의 href는 data-hydro JSON 안에 있어서
            # 텍스트에서 "owner / repo" 패턴으로 추출
            h2_text_match = re.search(
                r'<h2[^>]*>(.*?)</h2>', article, re.DOTALL
            )
            if not h2_text_match:
                continue
            h2_text = re.sub(r'<[^>]+>', ' ', h2_text_match.group(1))
            h2_text = re.sub(r'\s+', ' ', h2_text).strip()
            # "owner / repo" 또는 "owner/repo"
            name_match = re.search(r'([\w.-]+)\s*/\s*([\w.-]+)', h2_text)
            if not name_match:
                continue
            owner = name_match.group(1).strip()
            repo  = name_match.group(2).strip()

            # description
            desc_match = re.search(
                r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', article, re.DOTALL
            )
            description = ""
            if desc_match:
                description = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()

            # language
            lang_match = re.search(r'itemprop="programmingLanguage"[^>]*>\s*([^<]+)\s*<', article)
            language = lang_match.group(1).strip() if lang_match else ""

            # total stars (stargazers 링크 또는 텍스트에서)
            stars_match = re.search(r'href="/[^"]+/stargazers[^"]*"[^>]*>\s*<[^>]*>\s*([\d,]+)', article, re.DOTALL)
            if not stars_match:
                # 텍스트 전체에서 숫자 패턴 fallback
                plain = re.sub(r'<[^>]+>', ' ', article)
                nums = re.findall(r'([\d,]+)', plain)
                stars = max((int(n.replace(',','')) for n in nums), default=0)
            else:
                stars = int(stars_match.group(1).replace(",", ""))

            # stars this period (오늘/이번주/이번달 증가분)
            period_match = re.search(
                r'([\d,]+)\s+stars?\s+(?:today|this\s+week|this\s+month)',
                article, re.IGNORECASE
            )
            stars_period = int(period_match.group(1).replace(",", "")) if period_match else 0

            # topics
            topic_matches = re.findall(r'href="/topics/([^"]+)"', article)
            topics = topic_matches[:5]

            repos.append({
                "owner": owner,
                "repo": repo,
                "full_name": f"{owner}/{repo}",
                "description": description,
                "stars": stars,
                "stars_period": stars_period,
                "language": language,
                "url": f"https://github.com/{owner}/{repo}",
                "topics": topics,
            })
        except Exception:
            continue

    return repos


def clone_repo(owner: str, repo: str) -> Path:
    """얕은 클론 (--depth 1). 이미 있으면 fetch. 경로 반환."""
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", f"{owner}__{repo}")
    dest = CLONE_BASE / safe_name

    CLONE_BASE.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        # 이미 클론된 경우 최신화
        result = asyncio.get_event_loop().run_until_complete(
            _run_git(["git", "fetch", "--depth", "1"], cwd=dest)
        )
    else:
        clone_url = f"https://github.com/{owner}/{repo}.git"
        result = asyncio.get_event_loop().run_until_complete(
            _run_git(["git", "clone", "--depth", "1", clone_url, str(dest)])
        )

    return dest


CLONE_FETCH_TTL = 6 * 3600  # 6시간 이내 클론은 fetch 스킵


async def async_clone_repo(owner: str, repo: str) -> Path:
    """비동기 버전 클론. 이미 클론됐고 6시간 이내면 네트워크 호출 없이 재사용."""
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", f"{owner}__{repo}")
    dest = CLONE_BASE / safe_name
    CLONE_BASE.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        age = time.time() - dest.stat().st_mtime
        if age > CLONE_FETCH_TTL:
            await _run_git(["git", "fetch", "--depth", "1"], cwd=dest)
    else:
        clone_url = f"https://github.com/{owner}/{repo}.git"
        await _run_git(["git", "clone", "--depth", "1", clone_url, str(dest)])

    return dest


async def _run_git(args: list[str], cwd: Path = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(), stderr.decode()


def read_repo_summary(repo_path: Path, max_chars: int = 6000) -> str:
    """README + 파일 구조 요약 반환."""
    parts = []

    # README
    for name in ["README.md", "readme.md", "README.rst", "README.txt", "README"]:
        readme = repo_path / name
        if readme.exists():
            content = readme.read_text(encoding="utf-8", errors="ignore")
            if len(content) > 4000:
                content = content[:4000] + "\n...(이하 생략)"
            parts.append(f"## README\n\n{content}")
            break

    # 파일 구조 (2레벨)
    tree_lines = []
    try:
        for item in sorted(repo_path.iterdir()):
            if item.name.startswith(".") or item.name in ("node_modules", "__pycache__", ".git"):
                continue
            if item.is_dir():
                tree_lines.append(f"  {item.name}/")
                for sub in sorted(item.iterdir())[:8]:
                    if not sub.name.startswith("."):
                        tree_lines.append(f"    {sub.name}")
            else:
                tree_lines.append(f"  {item.name}")
    except Exception:
        pass

    if tree_lines:
        parts.append("## 파일 구조\n\n```\n" + "\n".join(tree_lines[:60]) + "\n```")

    # package.json / pyproject.toml / go.mod 등
    for meta_file in ["package.json", "pyproject.toml", "go.mod", "Cargo.toml", "requirements.txt"]:
        mp = repo_path / meta_file
        if mp.exists():
            content = mp.read_text(encoding="utf-8", errors="ignore")[:1000]
            parts.append(f"## {meta_file}\n\n```\n{content}\n```")
            break

    summary = "\n\n".join(parts)
    if len(summary) > max_chars:
        summary = summary[:max_chars] + "\n...(이하 생략)"
    return summary


def delete_clone(owner: str, repo: str) -> bool:
    """클론 디렉토리 삭제."""
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", f"{owner}__{repo}")
    dest = CLONE_BASE / safe_name
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
        return True
    return False


def list_clones() -> list[dict]:
    """로컬에 클론된 레포 목록."""
    if not CLONE_BASE.exists():
        return []
    result = []
    for d in sorted(CLONE_BASE.iterdir()):
        if d.is_dir():
            result.append({
                "name": d.name,
                "path": str(d),
                "size_mb": round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1024 / 1024, 1),
            })
    return result
