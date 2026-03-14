# A.R.C. (Agent Review Critic)

> Humor setting: 0%. Strictness setting: 100%.

A.R.C. does not write feature code. It exists solely to critique code written by other Agents (or humans) against architectural rubrics.

## Quick Start

```bash
# 1. Create venv and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env   # then edit with your keys

# 3. Run the server
uvicorn app.api.webhook_receiver:app --host 0.0.0.0 --port 8000
```

## Configuration

All config via environment variables (prefix `ARC_`), or `.env` file:

| Variable | Purpose | How to get |
|---|---|---|
| `ARC_GITHUB_TOKEN` | GitHub PAT for **target repo** (the repo being reviewed) | GitHub → Settings → Developer settings → Personal access tokens → Fine-grained token |
| `ARC_LLM_API_KEY` | Anthropic API key for Claude | console.anthropic.com → API Keys |
| `ARC_GITHUB_WEBHOOK_SECRET` | Webhook HMAC secret (optional for local dev) | GitHub App / Webhook settings |
| `ARC_LLM_MODEL` | LLM model ID (default: `claude-sonnet-4-20250514`) | — |
| `ARC_WATCH_DIR` | Local runner watch directory (default: `/tmp/arc_watch`) | — |

### GitHub Token Permissions

The token is for the **target repo being reviewed** (e.g. tars), not the arc repo itself.

**Fine-grained PAT required permissions:**
- `Pull requests`: Read & Write (fetch diff + post comments)
- `Contents`: Read (read file contents)

**Two auth options:**

| Option | Use case | Notes |
|------|---------|------|
| **Personal Access Token (PAT)** | Local dev, quick validation | Fastest, currently supported by default |
| **GitHub App** | Production, multi-repo | Requires code changes for App Auth, Phase 2 |

### .env Example

```env
ARC_GITHUB_TOKEN=github_pat_xxxxx
ARC_LLM_API_KEY=sk-ant-xxxxx
ARC_GITHUB_WEBHOOK_SECRET=
ARC_LLM_MODEL=claude-sonnet-4-20250514
```

## Architecture

```
GitHub PR Event
    │ Webhook POST
    ▼
┌──────────────────────────────┐
│  webhook_receiver.py         │
│  Verify signature → Extract  │
│  PR info → Background task   │
└──────────┬───────────────────┘
           │
    ┌──────▼──────┐     ┌─────────────────┐
    │ GitHubClient │────▶│ Fetch PR diff    │
    └──────┬──────┘     └─────────────────┘
           │
    ┌──────▼──────┐     ┌─────────────────┐
    │ CriticAgent  │────▶│ Rubrics + Diff   │
    │              │     │ → Claude API     │
    │              │     │ → JSON comments  │
    └──────┬──────┘     └─────────────────┘
           │
    ┌──────▼──────┐     ┌─────────────────┐
    │ GitHubClient │────▶│ Post PR comments │
    └─────────────┘     └─────────────────┘
```

### Module Responsibilities

| Module | Path | Job |
|--------|------|-----|
| **API Gateway** | `app/api/webhook_receiver.py` | Receive webhook, verify signature, dispatch |
| **Critic Agent** | `app/core/critic_agent.py` | Build prompt, call LLM, parse comments |
| **Rubric Parser** | `app/core/rubric_parser.py` | Load YAML rubrics |
| **GitHub Client** | `app/githandler/client.py` | PyGithub wrapper: fetch diff + post comments |
| **Actor Watchdog** | `app/local_runner/actor_watchdog.py` | Local polling, invoke Aider |
| **Config** | `config/settings.py` | Pydantic Settings, `ARC_` prefix |
| **Rubrics** | `rubrics/*.yaml` | Review rules (auto-loaded by default) |
