#!/usr/bin/env python3
"""harness-100 서브모듈 동기화 — 시스템 crontab에서 매일 04:00 KST 실행."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agents_registry


async def main():
    success = await agents_registry.sync_submodule()
    if success:
        print("[sync_harness] 동기화 완료")
    else:
        print("[sync_harness] 동기화 실패", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
