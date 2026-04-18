"""GitHub OAuth Device Flow + repo 관리.

사용자가 앱 UI에서 "GitHub 연결" 클릭 → Device Flow로 인증 → 토큰 로컬 DB 저장.
이후 repo 자동 생성, clone/pull, commit/push에 토큰 활용.

환경변수:
  GITHUB_CLIENT_ID — OAuth App의 Client ID (공개값, 소스에 포함 가능)
                     미설정 시 GITHUB_DEVICE_FLOW_DISABLED=true
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import httpx

import db

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path.home() / ".claude-local-workspaces"
GITHUB_API = "https://api.github.com"

# Device Flow에 필요한 스코프 (repo: 생성/read/write, user:email: 프로필)
_SCOPES = "repo user:email"


def client_id() -> Optional[str]:
    return os.environ.get("GITHUB_CLIENT_ID")


def is_configured() -> bool:
    return bool(client_id())


# ── 토큰 조회 (DB settings) ───────────────────────────────────────────────────

def get_token() -> Optional[str]:
    return db.get_setting("github_access_token")


def get_github_user() -> Optional[dict]:
    login = db.get_setting("github_user_login")
    avatar = db.get_setting("github_user_avatar")
    if not login:
        return None
    return {"login": login, "avatar_url": avatar}


def is_connected() -> bool:
    return bool(get_token())


def disconnect():
    db.set_setting("github_access_token", "")
    db.set_setting("github_user_login", "")
    db.set_setting("github_user_avatar", "")


# ── Device Flow ───────────────────────────────────────────────────────────────

async def start_device_flow() -> dict:
    """Device Flow 시작. user_code, verification_uri, device_code, interval 반환."""
    cid = client_id()
    if not cid:
        raise RuntimeError("GITHUB_CLIENT_ID가 설정되지 않았습니다.")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/device/code",
            data={"client_id": cid, "scope": _SCOPES},
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "device_code": data["device_code"],
        "user_code": data["user_code"],
        "verification_uri": data.get("verification_uri", "https://github.com/login/device"),
        "interval": data.get("interval", 5),
        "expires_in": data.get("expires_in", 900),
    }


async def poll_device_flow(device_code: str, interval: int = 5) -> Optional[str]:
    """토큰 폴링. 승인 완료되면 access_token 반환. 아직이면 None."""
    cid = client_id()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": cid,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    error = data.get("error")
    if error == "authorization_pending":
        return None
    if error == "slow_down":
        await asyncio.sleep(interval + 5)
        return None
    if error == "expired_token":
        raise RuntimeError("코드가 만료되었습니다. 다시 시작하세요.")
    if error == "access_denied":
        raise RuntimeError("사용자가 인증을 거부했습니다.")
    if error:
        raise RuntimeError(f"GitHub 오류: {error}")

    token = data.get("access_token")
    if token:
        # 사용자 정보 저장
        user = await _get_user(token)
        db.set_setting("github_access_token", token)
        db.set_setting("github_user_login", user.get("login", ""))
        db.set_setting("github_user_avatar", user.get("avatar_url", ""))
        logger.info("[github_oauth] 인증 완료: %s", user.get("login"))
    return token


# ── 사용자 / Repo API ─────────────────────────────────────────────────────────

async def _get_user(token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user",
            headers=_auth_headers(token),
        )
        resp.raise_for_status()
        return resp.json()


async def list_repos() -> list[dict]:
    """연결된 계정의 repo 목록 (최대 100개, 최근 업데이트 순)."""
    token = get_token()
    if not token:
        return []
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user/repos",
            params={"sort": "updated", "per_page": 100, "affiliation": "owner"},
            headers=_auth_headers(token),
        )
        resp.raise_for_status()
        return [
            {
                "full_name": r["full_name"],
                "name": r["name"],
                "private": r["private"],
                "default_branch": r["default_branch"],
                "description": r.get("description") or "",
                "html_url": r["html_url"],
            }
            for r in resp.json()
        ]


async def create_repo(name: str, description: str = "", private: bool = False) -> dict:
    """새 GitHub repo 생성. {full_name, html_url, clone_url} 반환."""
    token = get_token()
    if not token:
        raise RuntimeError("GitHub 미연결 상태입니다.")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/user/repos",
            json={
                "name": name,
                "description": description,
                "private": private,
                "auto_init": False,
            },
            headers=_auth_headers(token),
        )
        if resp.status_code == 422:
            # 이미 존재하는 repo
            user = get_github_user()
            login = user["login"] if user else ""
            return {
                "full_name": f"{login}/{name}",
                "html_url": f"https://github.com/{login}/{name}",
                "clone_url": f"https://github.com/{login}/{name}.git",
                "already_exists": True,
            }
        resp.raise_for_status()
        data = resp.json()
        return {
            "full_name": data["full_name"],
            "html_url": data["html_url"],
            "clone_url": data["clone_url"],
            "already_exists": False,
        }


# ── Git 작업 ──────────────────────────────────────────────────────────────────

async def init_and_push(dest: Path, repo_info: dict, message: str = "Initial commit by claude-local"):
    """로컬 디렉토리를 GitHub repo에 최초 push."""
    token = get_token()
    clone_url = _authed_url(repo_info["clone_url"], token)

    await _git(["git", "init"], cwd=dest)
    await _git(["git", "checkout", "-b", "main"], cwd=dest)
    await _git(["git", "add", "."], cwd=dest)
    # .claude/ 는 커밋 제외
    await _git(["git", "reset", "HEAD", ".claude/"], cwd=dest, check=False)
    rc, _, stderr = await _git(
        ["git", "commit", "-m", message,
         "--author", "claude-local <noreply@claude-local>"],
        cwd=dest, check=False
    )
    if rc != 0 and "nothing to commit" not in stderr:
        raise RuntimeError(f"git commit failed: {stderr}")
    await _git(["git", "remote", "add", "origin", clone_url], cwd=dest, check=False)
    await _git(["git", "remote", "set-url", "origin", clone_url], cwd=dest)
    rc, _, stderr = await _git(
        ["git", "push", "-u", "origin", "main", "--force"],
        cwd=dest
    )
    if rc != 0:
        raise RuntimeError(f"git push failed: {stderr}")


async def commit_and_push(dest: Path, message: str = "Update by claude-local"):
    """변경사항 commit + push."""
    token = get_token()
    await _git(["git", "add", "."], cwd=dest)
    await _git(["git", "reset", "HEAD", ".claude/"], cwd=dest, check=False)
    rc, _, stderr = await _git(
        ["git", "commit", "-m", message,
         "--author", "claude-local <noreply@claude-local>"],
        cwd=dest, check=False
    )
    if rc != 0 and "nothing to commit" not in stderr:
        logger.warning("[github_oauth] commit skipped: %s", stderr.strip())
        return
    rc, _, stderr = await _git(["git", "push"], cwd=dest)
    if rc != 0:
        raise RuntimeError(f"git push failed: {stderr}")


async def clone_or_pull(owner: str, repo: str, ref: str, dest: Path) -> str:
    """repo clone 또는 pull. HEAD SHA 반환."""
    token = get_token()
    clone_url = _authed_url(f"https://github.com/{owner}/{repo}.git", token)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if (dest / ".git").exists():
        await _git(["git", "fetch", "--depth", "1", "origin", ref], cwd=dest)
        await _git(["git", "reset", "--hard", f"origin/{ref}"], cwd=dest)
    else:
        await _git(["git", "clone", "--depth", "1", "--branch", ref, clone_url, str(dest)])
        # harness 생성 파일이 실수로 커밋되지 않도록
        exclude = dest / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        content = exclude.read_text() if exclude.exists() else ""
        if ".claude/" not in content:
            exclude.write_text(content + "\n.claude/\n")

    rc, sha, _ = await _git(["git", "rev-parse", "HEAD"], cwd=dest, check=False)
    return sha.strip() if rc == 0 else ""


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def repo_slug(text: str) -> str:
    """보드 이름 → GitHub repo slug 변환."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:100] or "claude-local-project"


def workspace_for_board(board_id: int) -> Path:
    return WORKSPACE_ROOT / str(board_id)


def _auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _authed_url(url: str, token: Optional[str]) -> str:
    if not token:
        return url
    return url.replace("https://", f"https://oauth2:{token}@")


async def _git(args: list[str], cwd: Path = None, check: bool = True) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    stdout, stderr = await proc.communicate()
    rc = proc.returncode
    if check and rc != 0:
        raise RuntimeError(f"{' '.join(args)}: {stderr.decode().strip()}")
    return rc, stdout.decode(), stderr.decode()
