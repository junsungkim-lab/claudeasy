# claudeasy

> **Just say it — AI builds it** — A local multi-agent orchestration platform powered by Claude Code

**[한국어](README.md) | English**

![Request Flow](docs/diagram-nodes.png)

Describe what you want, and AI assembles a team of specialists, breaks it into tasks, and builds it in real time.  
No coding required — from automation scripts to web apps and recurring bots.

---

## Execution Flow

![4-Step Execution Flow](docs/diagram-flow.png)

---

## System Architecture

![System Architecture](docs/diagram-arch.png)

---

## Key Features

| Feature | Description |
|---------|-------------|
| 🤖 **Multi-Agent Orchestration** | One request → expert team + task graph, auto-generated |
| ⚡ **Real-Time Streaming** | Card output streamed character-by-character via WebSocket |
| 🔗 **Dependency-Based Execution** | Cycle detection, failure propagation, parallel independent tasks |
| 🗓️ **Automation & Scheduling** | Natural language ("every day at 9am") → cron auto-registered |
| 📦 **Artifact Auto-Detection** | Detects uvicorn, npm run dev, streamlit, flask, etc. → Run button |
| 🔍 **3-Layer Artifact Validation** | Parse normalization → save gate → failure visualization |
| 🛡️ **SDK Auto-Block** | If LLM uses Anthropic SDK, it's automatically removed and replaced with CLI subprocess |
| 📋 **Publish Queue** | Queue topics/URLs for blog & SNS automation boards — published one per day |
| 🔒 **Sensitive Info Guard** | Password/API key questions escalate to the user instead of auto-answering |
| 🌐 **GitHub Integration** | OAuth + GitHub Trending analysis + apply to your project |
| 🔔 **Notifications** | Telegram / Email push notifications |
| 📚 **harness-100 Library** | 10 domains, 489 agents, 315 skills built-in |

---

## Quick Start

### Prerequisites

- [Claude Code CLI](https://claude.ai/code) installed + authenticated (**required**)
- Python 3.9+
- Node.js 18+ or [Bun](https://bun.sh)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/junsungkim-lab/claudeasy.git
cd claudeasy

# 2. Python dependencies
pip install -r requirements.txt

# 3. Frontend dependencies
cd web && bun install && cd ..

# 4. Environment variables (optional)
cp .env.example .env
```

### Run

```bash
python3 server.py
```

Open [http://localhost:8100](http://localhost:8100) in your browser

> **Dev mode** (hot reload): Run `cd web && bun run dev` in a separate terminal and open [http://localhost:5173](http://localhost:5173)

---

## How to Use

### Step 1: Describe what you want

Type your request in natural language into the main input.

```
# Build a project
Build a Todo app with React + FastAPI

# Recurring automation (cron auto-registered)
Every day at 8am, fetch exchange rates and send to Telegram

# Content automation (publish queue auto-created)
Automate SEO blog posts on Naver. Publish daily at 10am.
```

### Step 2: Agent team auto-assembled

Within seconds, Claude designs a specialist team and creates task cards.

```
Example: "Naver blog automation" request

  [Card 1] Project initialization & structure     backend-dev   → done
  [Card 2] URL scraper module                     backend-dev   → done
  [Card 3] SEO analyzer + post generator          backend-dev   → done
  [Card 4] Playwright Naver blog uploader         backend-dev   → done
  [Card 5] Pipeline integration + schedule        backend-dev   → done
  [Card 6] Integration QA & validation            qa-engineer   → done
```

### Step 3: Choose execution mode

| Mode | Behavior |
|------|----------|
| **Auto** | Cards run sequentially without intervention (default) |
| **Manual Approval** | Approve or Reject each card before it runs |

### Step 4: Run your artifact

In the **Results** tab, run the generated server or script directly.

- **Server** → Click `Run Server` → runs in background + port link auto-generated
- **Script** → Click `Run`
- If the process crashes within 5 seconds, stderr is shown immediately in a red error box
- If env vars are needed, an input form appears automatically before execution

### Step 5: Publish Queue (content automation)

Boards for blog/SNS automation show a **Publish Queue** panel at the bottom of the Results tab.

- Add topics (text) or `https://` URLs to the queue
- Optionally add instructions (tone, target audience, emphasis)
- Items are published one per day in order
- Last 5 published items shown in history

```
Queue example:
  1. Spring 2026 healthy diet trends    →  publishing today
  2. https://example.com/product        →  publishing tomorrow
  3. Diet supplement comparison review  →  publishing the day after
```

### Step 6: Schedule management (automation boards)

Board header → 🕐 schedule icon.

```
Supported natural language:
  every day at 9am          →  0 9 * * *
  every Monday at 10am      →  0 10 * * 1
  every 30 minutes          →  */30 * * * *
  every hour                →  0 * * * *
```

---

## 3-Layer Artifact Validation

LLM-generated execution metadata (cwd, run command, type) is validated at three layers to prevent bad configurations from reaching users.

```
Layer 1 — Parse Normalization (harness.py)
  - cwd outside project → auto-corrected to project_path
  - type declared as "server" with no server keywords → downgraded to "script"
  - dangling --flag with no value → warning emitted

Layer 2 — Save Gate (server.py)
  - empty run_command → rejected, Run button not shown
  - missing cwd directory → rejected
  - missing script file → rejected
  - warnings attached as card output markers + UI badge

Layer 3 — Failure Visualization (server.py)
  - process exit within 5 seconds detected
  - stderr tail (up to 2000 chars) shown in red box below Run button
  - real-time WebSocket artifact_failed event
```

---

## Anthropic SDK Auto-Block

This platform calls AI exclusively via Claude Code CLI (`claude -p`). The `anthropic` Python package is not installed. Even if the LLM writes SDK code, it's automatically replaced.

**Auto-replacement behavior (`_sanitize_sdk_usage`)**:

| Target | Action |
|--------|--------|
| `import anthropic` / `from anthropic import ...` | Line removed + Claude CLI subprocess snippet injected |
| `anthropic` entry in `requirements.txt` | Auto-removed |
| `ANTHROPIC_API_KEY` in `.env` / `.env.example` | Auto-removed |

Every `.py` file in the project is scanned on card completion. Replaced files are listed in the card warning marker.

---

## Project Context Files

Agents automatically reference two files in the project root.

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project overview, tech stack, constraints |
| `MEMORY.md` | Work history, decisions, accumulated knowledge |

Optional but highly recommended — agents understand the project much better with them.

---

## GitHub Trending Analysis

Header → `GitHub Trending` button

1. Filter trending repos by language / time period
2. Click **Analyze** on any repo → shallow clone + Claude analysis
3. Click **Apply Analysis** → instantly create a development board

> **Tip**: Select your project in the sidebar first, and the analysis becomes "how to apply this repo to my project" rather than a generic overview.

---

## Environment Variables

`.env` file (all optional):

```bash
# Tavily real-time web search (enriches harness generation context)
TAVILY_API_KEY=

# Server port (default: 8100)
PORT=8100
```

> **No Anthropic API Key needed** — Claude Code CLI is already authenticated.

Notification settings (Telegram / Email) are configured in the **Settings** page in the UI.

---

## Core Files

| File | Role |
|------|------|
| `server.py` | FastAPI app, 50+ API endpoints, WebSocket handlers |
| `harness.py` | Harness generation, card execution, artifact parsing + normalization + SDK blocking |
| `db.py` | SQLite schema, CRUD, auto-migration |
| `scheduler.py` | crontab integration, schedule registration/removal |
| `notifier.py` | Telegram / Email notifications |
| `github_trending.py` | Trending repo scraping + Claude analysis |
| `web/` | React 19 + TypeScript frontend |
| `harness-100/` | 100 production harness library entries |

---

## Screenshots

<table>
<tr>
<td><img src="docs/01-main.png" alt="Main screen" /></td>
<td><img src="docs/02-board-view.png" alt="Board results" /></td>
</tr>
<tr>
<td align="center"><b>Main screen</b> — project list + request input</td>
<td align="center"><b>Board view</b> — all 6 cards completed</td>
</tr>
<tr>
<td colspan="2"><img src="docs/03-trending.png" alt="GitHub Trending" /></td>
</tr>
<tr>
<td colspan="2" align="center"><b>GitHub Trending</b> — trending repo analysis + apply to your project</td>
</tr>
</table>

---

## License

MIT
