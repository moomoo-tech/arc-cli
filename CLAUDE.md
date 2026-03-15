# CLAUDE.md

This file provides guidance to Claude Code when working on this repository.

## Project Overview

A.R.C. (Adversarial Resolution Cycle) is a CLI tool that pits two LLMs against each other: a Critic reviews code, an Agent fixes it, they debate in structured JSON threads until convergence.

- **Language:** Python 3.12+
- **License:** Apache 2.0

## Commands

```bash
pip install -e ".[dev]"              # install with all deps + pytest
pytest                                # run tests (50+)
python arc.py                         # review current repo
python arc.py --fix --max-turns 5     # Agent vs Critic loop
```

## Architecture

- **`arc.py`** — CLI entry point. Parses args, runs fix loop, prints Battle Report.
- **`app/context.py`** — Reads repo via `git ls-files` with noise filtering (200KB cap).
- **`app/core/critic_agent.py`** — Critic prompts (free-form + stateful JSON). Parses LLM JSON responses. Generates audit report.
- **`app/core/rubric_parser.py`** — Loads YAML rubric rules from `rubrics/`.
- **`app/core/utils.py`** — `is_double_jeopardy()` fuzzy matching (file + snippet + line radius).
- **`app/llm/`** — Multi-provider LLM abstraction. `base.py` ABC, `factory.py` creates by provider name. Gemini client tracks token usage.
- **`config/settings.py`** — Pydantic Settings from `.env` (prefix `ARC_`).

## Key Design Decisions

- **Blackboard Pattern**: Issues tracked as `Dict[ISSUE-ID, {status, file, approx_line, snippet, history}]`
- **Democratic debate**: Neither Critic nor Agent has veto. Deadlocks go to human.
- **Status tags** (`[NEW]`, `[REOPEN]`, `[VERIFIED]`, `[ACKED]`) are injected into history content so both LLMs see them in context.
- **Double Jeopardy**: Settled issues blocked from re-filing (fuzzy ±5 line radius + snippet containment).
- **Absolute lock**: Once resolved/acknowledged, cannot be reopened by Critic.
- **Agent uses Claude Code CLI** (`claude -p`) via subprocess, not the Anthropic SDK — it needs `Read`/`Edit`/`Bash` tools to modify files.

## Configuration

All via environment variables (prefix `ARC_`) or `.env` file:

| Variable | Purpose |
|---|---|
| `ARC_LLM_PROVIDER` | `anthropic`, `openai`, or `gemini` |
| `ARC_LLM_API_KEY` | API key |
| `ARC_LLM_MODEL` | Model ID |
