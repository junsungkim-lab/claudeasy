#!/usr/bin/env python3
"""시스템 crontab에서 호출되는 보드 실행 스크립트.

Usage: python3 run_board.py <board_id> [port]
"""
import sys
import urllib.request
import urllib.error
import json

def main():
    if len(sys.argv) < 2:
        print("Usage: run_board.py <board_id> [port]", file=sys.stderr)
        sys.exit(1)

    board_id = int(sys.argv[1])
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8100
    url = f"http://localhost:{port}/api/boards/{board_id}/schedule/trigger"

    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            print(f"[run_board] board={board_id} run_id={body.get('run_id')} OK")
    except urllib.error.HTTPError as e:
        print(f"[run_board] HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[run_board] Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
