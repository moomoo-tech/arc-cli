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

### GitHub Token 权限

Token 是给**被审查的目标仓库**的（比如 tars），不是 arc 自己的仓库。

**Fine-grained PAT 所需权限：**
- `Pull requests`: Read & Write（拉 diff + 发评论）
- `Contents`: Read（读取文件内容）

**两种 Auth 方案：**

| 方案 | 适用场景 | 说明 |
|------|---------|------|
| **Personal Access Token (PAT)** | 本地开发、快速验证 | 最快，当前代码默认支持 |
| **GitHub App** | 生产部署、多仓库 | 需改代码支持 App Auth，Phase 2 |

### .env 示例

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
│  验签 → 提取 PR 信息 →       │
│  后台任务 dispatch            │
└──────────┬───────────────────┘
           │
    ┌──────▼──────┐     ┌─────────────────┐
    │ GitHubClient │────▶│ 拉 PR diff       │
    └──────┬──────┘     └─────────────────┘
           │
    ┌──────▼──────┐     ┌─────────────────┐
    │ CriticAgent  │────▶│ Rubrics + Diff   │
    │              │     │ → Claude API     │
    │              │     │ → JSON comments  │
    └──────┬──────┘     └─────────────────┘
           │
    ┌──────▼──────┐     ┌─────────────────┐
    │ GitHubClient │────▶│ 发 PR 评论       │
    └─────────────┘     └─────────────────┘
```

### Module Responsibilities

| Module | Path | Job |
|--------|------|-----|
| **API Gateway** | `app/api/webhook_receiver.py` | 收 webhook，验签，dispatch |
| **Critic Agent** | `app/core/critic_agent.py` | 拼 prompt，调 LLM，解析评论 |
| **Rubric Parser** | `app/core/rubric_parser.py` | 加载 YAML rubrics |
| **GitHub Client** | `app/githandler/client.py` | PyGithub 封装：拉 diff + 发评论 |
| **Actor Watchdog** | `app/local_runner/actor_watchdog.py` | 本地轮询，触发 Aider |
| **Config** | `config/settings.py` | Pydantic Settings，`ARC_` 前缀 |
| **Rubrics** | `rubrics/*.yaml` | 审查规则（默认自动加载） |
