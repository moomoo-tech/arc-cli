# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A.R.C. (Agent Review Critic) is a CLI tool that reviews code against architectural rubrics (YAML rule files). It brute-force reads your entire repo, sends it with the git diff to Claude via native Tool Use, and gets back a review with optional auto-fixes.

- **Language:** Python 3.12+
- **License:** Apache 2.0

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run a review on the current repo
python arc.py

# Review a specific repo
python arc.py /path/to/repo

# Review only (no auto-fixes)
python arc.py --review-only

# Use custom rubrics
python arc.py --rubrics my_rules.yaml
```

## Architecture

Three modules, dead simple:

- **`arc.py`** — CLI entry point (argparse). Orchestrates the flow: diff → context → agent loop → output.
- **`app/context.py`** — Brute-force repo context builder. Walks the entire repo, packs all code files into one string. No AST, no optimization.
- **`app/core/critic_agent.py`** — Pure Claude Agent Loop. Sends rubrics + diff + full repo to Claude with Tool Use. Claude reviews and calls `apply_code_patch` to fix issues directly.
- **`app/core/rubric_parser.py`** — YAML rubric loader. Reads `rubrics/*.yaml` and formats rules for the prompt.

### Flow

1. `arc.py` runs `git diff` and reads the entire repo into a string.
2. Sends everything (rubrics + diff + full codebase) to Claude in one shot.
3. Claude reviews against rubrics, calls `apply_code_patch` tool to fix issues.
4. Python executes the search-and-replace on disk, feeds result back to Claude.
5. Loop until Claude stops calling tools. Print summary.

## Configuration

Environment variables (prefix `ARC_`) or `.env` file:

| Variable | Purpose |
|---|---|
| `ARC_LLM_API_KEY` | Anthropic API key |
| `ARC_LLM_MODEL` | LLM model ID (default: claude-sonnet-4-20250514) |
