"""
CLI로 파이프라인 실행
Usage: python3 run_pipeline.py "태스크 내용"
       python3 run_pipeline.py "태스크 내용" --agents agents.json
       python3 run_pipeline.py "태스크 내용" --out ./my_output
"""
import asyncio
import json
import sys
from pathlib import Path
from pipeline import run_pipeline, DEFAULT_AGENTS, Agent

COLORS = {
    "PM":       "\033[94m",   # 파랑
    "Designer": "\033[95m",   # 보라
    "Dev":      "\033[92m",   # 초록
    "QA":       "\033[93m",   # 노랑
    "reset":    "\033[0m",
    "dim":      "\033[2m",
    "bold":     "\033[1m",
}


def colorize(role: str, text: str) -> str:
    color = COLORS.get(role, "\033[97m")
    return f"{color}{text}{COLORS['reset']}"


async def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    task = args[0]
    agents = DEFAULT_AGENTS
    output_dir = Path("./pipeline_output")

    # 인수 파싱
    i = 1
    while i < len(args):
        if args[i] == "--agents" and i + 1 < len(args):
            with open(args[i + 1]) as f:
                agents = [Agent(**a) for a in json.load(f)]
            i += 2
        elif args[i] == "--out" and i + 1 < len(args):
            output_dir = Path(args[i + 1])
            i += 2
        else:
            i += 1

    print(f"\n{COLORS['bold']}Pipeline 시작{COLORS['reset']}")
    print(f"태스크: {task[:80]}{'...' if len(task) > 80 else ''}")
    print(f"에이전트: {' → '.join(a.role for a in agents)}")
    print(f"출력 디렉토리: {output_dir}\n")
    print("─" * 60)

    current_role = None

    def on_event(event: dict):
        nonlocal current_role
        t = event.get("type")

        if t == "stage_start":
            role = event["role"]
            current_role = role
            provider = event["provider"]
            model = event["model"]
            print(f"\n{colorize(role, f'▶ [{role}]')} {COLORS['dim']}{provider} / {model}{COLORS['reset']}")

        elif t == "chunk":
            print(event["chunk"], end="", flush=True)

        elif t == "stage_done":
            role = event["role"]
            print(f"\n{colorize(role, f'✓ [{role}] 완료')} → {event['output_file']}")
            print("─" * 60)

        elif t == "pipeline_done":
            print(f"\n{COLORS['bold']}모든 스테이지 완료 ({event['stages']}개){COLORS['reset']}")
            print(f"결과물: {output_dir}/\n")

        elif t == "error":
            print(f"\n\033[91m오류: {event['message']}\033[0m")

    await run_pipeline(task, agents=agents, output_dir=output_dir, on_event=on_event)


if __name__ == "__main__":
    asyncio.run(main())
