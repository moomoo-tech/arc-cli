# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A.R.C. (Agent Review Critic) is a code review agent that critiques code written by other agents or humans against architectural rubrics (YAML rule files). It does not write feature code — it exists solely to review and critique.

- **Language:** Python 3.12+
- **License:** Apache 2.0

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app.api.webhook_receiver:app --host 0.0.0.0 --port 8000

# Docker
docker build -t arc .
docker run -p 8000:8000 --env-file .env arc
```

## Architecture

Four modules under `app/`, each with a single responsibility:

- **`app/api/`** — FastAPI gateway. Receives GitHub webhooks, validates signatures, dispatches to the critic agent. Entry point: `webhook_receiver.py`.
- **`app/core/`** — The "brain". `critic_agent.py` assembles prompts from rubrics + diffs and calls the LLM. `rubric_parser.py` loads and formats YAML rule files from `rubrics/`.
- **`app/githandler/`** — PyGithub wrapper. `client.py` fetches PR diffs and posts review comments back to GitHub.
- **`app/local_runner/`** — Local "hands". `actor_watchdog.py` polls a directory for instruction files and invokes Aider to act on review feedback.

Supporting directories:

- **`rubrics/`** — YAML rubric files (global default rules). Each file has a `rules` list with `name`, `description`, `severity`.
- **`config/settings.py`** — Pydantic Settings loaded from env vars prefixed with `ARC_` (or `.env` file).

## Configuration

All config via environment variables (prefix `ARC_`):

| Variable | Purpose |
|---|---|
| `ARC_GITHUB_TOKEN` | GitHub API token |
| `ARC_GITHUB_WEBHOOK_SECRET` | Webhook HMAC secret |
| `ARC_LLM_API_KEY` | LLM API key |
| `ARC_LLM_MODEL` | LLM model ID |
| `ARC_WATCH_DIR` | Local runner watch directory |
