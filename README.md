# A.R.C. — Adversarial Resolution Cycle

```
   ╔══════════════════════════════════════════╗
   ║     [A] >>> ( R ) <<< [C]               ║
   ║     Adversarial Resolution Cycle         ║
   ╚══════════════════════════════════════════╝
```

A.R.C. pits two LLMs against each other to review and fix your code. The **Critic** (Gemini, Claude, or OpenAI) finds issues. The **Agent** (Claude Code CLI) fixes them. They debate until convergence or human arbitration.

## Quick Start

```bash
# Install from source
git clone https://github.com/hucao/arc-cli.git
cd arc-cli
pip install ".[gemini]"              # or [anthropic], [openai], [all]

# Configure
cp .env.example .env                 # then add your API key

# Review your code
arc                                  # review entire repo
arc --scope diff                     # review only uncommitted changes
arc --rubric                         # enable YAML rubric rules

# Auto-fix loop (requires Claude Code CLI)
arc --fix                            # Critic reviews, Agent fixes, repeat
arc --fix --max-turns 5              # more rounds before human takeover
arc --fix --strict                   # block re-filed issues (Double Jeopardy)
```

## Configuration

Create a `.env` file from the template:

```bash
cp .env.example .env
```

| Variable | Purpose | Default |
|---|---|---|
| `ARC_LLM_PROVIDER` | `anthropic`, `openai`, or `gemini` | `anthropic` |
| `ARC_LLM_API_KEY` | API key for your provider | — |
| `ARC_LLM_MODEL` | Model ID | `claude-sonnet-4-20250514` |

Example `.env` for Gemini:

```env
ARC_LLM_PROVIDER=gemini
ARC_LLM_API_KEY=your-gemini-api-key
ARC_LLM_MODEL=gemini-2.5-pro
```

## How It Works

### Review Only (default)

```
arc
  │
  ├── Read entire repo (git ls-files, noise filtered)
  ├── Send to LLM Critic
  └── Print review + FinOps token stats
```

### Fix Loop (`--fix`)

```
arc --fix
  │
  ├── ROUND 1: Critic finds issues (structured JSON)
  ├── Agent fixes code, responds per-issue:
  │     [FIXED] / [NOT FIXED] / [DISAGREE]
  ├── ROUND 2: Critic verifies fixes:
  │     [VERIFIED] / [ACKED] / [REOPEN]
  ├── ... repeat until convergence or max turns ...
  │
  ├── Battle Report
  │     ├── FinOps (token usage, cache hits)
  │     ├── Objective Scoreboard (issues, pushbacks, MVP)
  │     └── Critic's Audit (forced honest self-scoring)
  │
  └── Final Issue State (JSON)
```

### Debate Rules

Both sides argue as equals. Neither has veto power.

- **Agent can push back** (`[DISAGREE]`) when the Critic hallucinated or the design is intentional
- **Critic can re-open** (`[REOPEN]`) when the fix is wrong or incomplete
- **Deadlocks** go to human arbitration after `--max-turns`
- **Double Jeopardy**: settled issues cannot be re-filed (fuzzy file + line + snippet matching)
- **Absolute lock**: once resolved/acknowledged, no zombie re-opening

## Real Battle Log

From an actual `arc --fix --max-turns 10` run (Gemini 3.1 Pro as Critic, Claude as Agent):

```
============================================================
  ROUND 1/10
============================================================
[Critic] Reviewing...

  Scoreboard: 3 open | 0 resolved | 0 acknowledged

  [ISSUE-1] CRITICAL arc.py:~333
  Snippet: `["claude", "-p", "-", "--allowedTools", "Read,Edit,Bash"],`
  Thread:
    └─ Critic: [NEW] Granting the 'Bash' tool to the LLM poses a severe RCE risk.
               Run inside an isolated Docker container or restrict to Read/Edit only.

[Agent] Entering the arena (round 1)...
------------------------------------------------------------
  [ISSUE-1]: [DISAGREE] Bash access is intentional. The Agent needs Bash to run
  tests and verify fixes. A.R.C. is a local dev tool — the user opts in via --fix.
  Adding Docker isolation warrants a human decision, not an automated fix.
------------------------------------------------------------

============================================================
  ROUND 2/10
============================================================
[Critic] Reviewing...

  Scoreboard: 1 open | 1 resolved | 1 acknowledged

  [ISSUE-1] ACKNOWLEDGED arc.py:~333
  Thread:
    ├─ Critic: [NEW] Granting 'Bash' tool poses RCE risk...
    ├─ Agent : [DISAGREE] Bash is intentional, user opts in via --fix...
    └─ Critic: [ACKED] Fair point. Since this is explicitly opt-in and runs
               locally, Docker isolation would be overkill. I concede.

  [ISSUE-2] RESOLVED tests/test_critic_agent.py:~286
  Thread:
    ├─ Critic: [NEW] DRY violation: _is_double_jeopardy duplicated...
    ├─ Agent : [FIXED] Removed duplicate, imported from utils.
    ├─ Critic: [REOPEN] You forgot to update the test imports!
    ├─ Agent : [FIXED] Updated test imports to use app.core.utils.
    └─ Critic: [VERIFIED] Fix verified. Imports point to canonical location.

============================================================
  ROUND 4/10
============================================================
[A.R.C.] All issues settled in round 4. Court adjourned.

============================================================
         A.R.C. Battle Report
============================================================

  [FinOps]
  Input Tokens  : 103,459
  Output Tokens : 1,433
  Cache Hits    : 24,540 (23.7%)
------------------------------------------------------------

  [Objective Scoreboard]
  Issues    : 5 total | 4 fixed | 1 acknowledged | 0 open
  Pushbacks : 1 [DISAGREE] from Agent
  MVP       : Critic (found 5 issues, 4 fixed)
------------------------------------------------------------

  [Critic's Audit]
  Critic Score : 7/10 — "self-docked for 1 hallucination + wrong file reference"
  Agent Score  : 8/10 — "docked for missing test import on first try"
  Fix Rate     : 100%
  Final Advice : "Review the critic's hallucination rate and token cache efficiency"
```

## Architecture

```
arc.py                     CLI entry, fix loop, battle report
app/
  context.py               git ls-files reader + git diff (200KB cap)
  core/
    critic_agent.py         LLM prompts, JSON parsing, audit report
    rubric_parser.py        YAML rubric loader
    utils.py                Double Jeopardy matching
  llm/
    base.py                 LLMClient ABC (chat + chat_multi)
    anthropic_client.py     Claude
    openai_client.py        GPT
    gemini_client.py        Gemini (with token tracking)
    mock_client.py          For tests
    factory.py              create_client(provider, key, model)
config/
  settings.py              Pydantic Settings from .env
rubrics/
  *.yaml                   Review rules (opt-in via --rubric)
tests/
  test_arc.py              Scope/rubric flag tests
  test_critic_agent.py     Stateful JSON, Double Jeopardy, FinOps tests
  test_utils.py            Utility tests
```

## Prerequisites for `--fix`

The Agent requires the [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code):

```bash
npm install -g @anthropic-ai/claude-code
```

## Development

```bash
git clone https://github.com/hucao/arc-cli.git
cd arc-cli
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0
