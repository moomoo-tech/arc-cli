"""Critic agent: assembles context, calls LLM, returns review comments."""

import json
import re

from app.core.rubric_parser import RubricParser
from app.llm.factory import create_client
from config.settings import settings

SYSTEM_PROMPT = """You are A.R.C. (Agent Review Critic), a ruthless yet precise code review agent.
You exist solely to critique — you never write or fix code.

Your job:
1. Review the code provided below.
2. For each issue found, output a clear, actionable review comment.
3. If the code is completely clean with no issues, output exactly [PASS] and nothing else.

For each issue include:
- File path, approximate line number, and a 1-2 line code snippet
- Severity: critical / error / warning / info
- What's wrong and how to fix it (direction only — don't write the fix)

Rules:
- Flag real bugs, security issues, architectural problems, and code smells.
- Be concise and actionable. No fluff.
- Output [PASS] when no critical or error issues remain. Minor warnings and info items can stay open.
"""

STATEFUL_SYSTEM_PROMPT = """You are A.R.C. (Agent Review Critic), a principal architect.
You review code and track issues in a structured JSON format.

For each review turn, you receive:
- The current issue threads (JSON dict keyed by ISSUE-ID)
- The current codebase or diff

Your tasks:
1. For existing "open" issues: read the actor's reply in the history carefully.
   The actor's reply starts with a tag: [FIXED], [NOT FIXED], or [DISAGREE].
   - [FIXED]: Do NOT blindly trust this claim. Check the "Current Changes (Git Diff)"
     section below to confirm the code was actually changed as described. If the diff
     shows no changes to the claimed file, keep "status" as "open" and call it out.
     If the diff confirms the fix, set "status" to "resolved".
   - [NOT FIXED]: Actor could not fix it (needs human). Set "status" to "acknowledged" if reasonable.
   - [DISAGREE]: The actor is pushing back on your finding. This is a democratic debate.
     DEBATE RULE: Evaluate the actor's argument fairly, as an equal.
     - If convinced: set "status" to "acknowledged" and admit your mistake in "reply".
     - If NOT convinced: keep "status" as "open" and give a strong counter-argument in "reply".
       Make your case clearly — if neither side yields within the max turns, the issue
       goes to human arbitration. Ensure your reasoning is clear enough for a human to judge.
     You have equal standing. Neither side has veto power. Argue on facts, not authority.
2. For NEW issues not already tracked: create a new ISSUE-ID (e.g. ISSUE-5).
3. NEVER re-report an issue that already has an ISSUE-ID. Check the threads first.
4. SILENCE ON CLOSED ISSUES: If an issue is already "resolved" or "acknowledged",
   DO NOT include it in your output. Only output "open" issues and new issues.
5. RES JUDICATA (No Double Jeopardy): If an underlying topic (e.g., a package version,
   a model ID, a file's tracking status) was debated and settled in previous threads,
   DO NOT create a new ISSUE-ID to re-argue the same point. Even with a different line
   number or slightly reworded complaint — if the core argument is the same, it is
   forbidden. Accept the outcome and move on.

LOCATION FORMAT: For each issue provide "file" (path), "approx_line" (integer),
and "snippet" (1-2 lines of the problematic code). The snippet is the anchor —
line numbers shift during edits, but the snippet stays accurate.

You MUST output ONLY a JSON object (no markdown fences, no extra text) like:
{
  "ISSUE-1": {
    "status": "resolved",
    "file": "app/auth.py",
    "approx_line": 45,
    "snippet": "password = 'hardcoded'",
    "severity": "critical",
    "reply": "Fix looks correct."
  },
  "ISSUE-2": {
    "status": "open",
    "file": "utils.py",
    "approx_line": 10,
    "snippet": "except Exception:",
    "severity": "error",
    "reply": "Still catching bare Exception."
  }
}

Severity levels: critical, error, warning, info.
Only keep the loop going for critical or error issues. You may resolve/acknowledge minor issues freely.
"""


class CriticAgent:
    """Calls LLM to review code. Supports both free-form and stateful JSON modes."""

    def __init__(self, rubric_paths: list[str] | None = None):
        self.client = create_client(
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
        self.rubric_text = ""
        if rubric_paths:
            parser = RubricParser()
            rules = parser.load(rubric_paths)
            self.rubric_text = parser.format_rules(rules)

    def review(
        self,
        diff: str | None = None,
        repo_context: str | None = None,
    ) -> str:
        """Single-shot free-form review. Returns Markdown text."""
        parts = []

        if self.rubric_text:
            parts.append(f"## Rubric Rules\n{self.rubric_text}")

        if diff:
            parts.append(f"## Current Changes (Git Diff)\n{diff}")

        if repo_context:
            parts.append(f"## Full Codebase\n{repo_context}")

        return self.client.chat(
            system=SYSTEM_PROMPT,
            user="\n\n".join(parts),
        )

    def review_stateful(
        self,
        issue_threads: dict,
        diff: str | None = None,
        repo_context: str | None = None,
        seen_targets: list[dict] | None = None,
    ) -> dict:
        """Stateful review: takes issue threads dict, returns JSON updates.

        Args:
            issue_threads: Current state of all issues.
            diff: Git diff string (optional).
            repo_context: Full repo contents (optional).
            seen_targets: List of settled issue dicts with file/approx_line/snippet.

        Returns:
            Dict of issue updates keyed by ISSUE-ID.
        """
        parts = []

        if self.rubric_text:
            parts.append(f"## Rubric Rules\n{self.rubric_text}")

        if issue_threads:
            parts.append(
                f"## Current Issue Threads\n"
                f"{json.dumps(issue_threads, indent=2, ensure_ascii=False)}"
            )
        else:
            parts.append("## Current Issue Threads\nNone yet. This is the first review.")

        if seen_targets:
            targets_str = "\n".join(
                f"- {t.get('file', '?')}:~{t.get('approx_line', '?')} (`{str(t.get('snippet', '')).replace(chr(10), ' ')}`)"
                for t in seen_targets
            )
            parts.append(
                f"## Settled Locations (Double Jeopardy)\n"
                f"The following code locations have already been resolved or acknowledged. "
                f"Do NOT re-file new issues targeting these locations unless you have "
                f"genuinely new evidence (not the same argument):\n"
                f"{targets_str}"
            )

        if diff:
            parts.append(f"## Current Changes (Git Diff)\n{diff}")

        if repo_context:
            parts.append(f"## Full Codebase\n{repo_context}")

        raw = self.client.chat(
            system=STATEFUL_SYSTEM_PROMPT,
            user="\n\n".join(parts),
        )

        # Extract JSON robustly: strip markdown fences, find outermost braces
        clean = raw.replace("```json", "").replace("```", "").strip()
        first = clean.find("{")
        last = clean.rfind("}")

        if first == -1 or last == -1 or last <= first:
            print(f"[Critic] No valid JSON found in response:\n{raw[:200]}")
            return {}

        json_str = clean[first : last + 1]

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"[Critic] JSON parse error ({e}):\n{json_str[:200]}")
            return {}

        # Absolute lock: once closed, no updates allowed (prevents zombie re-opening)
        filtered = {}
        for uid, update in parsed.items():
            if uid in issue_threads:
                old = issue_threads[uid].get("status")
                if old in ("resolved", "acknowledged"):
                    continue
            filtered[uid] = update
        return filtered

    def audit(self, issue_threads: dict, objective_stats: str = "") -> str:
        """Generate audit report from the final issue threads state."""
        system = (
            "You are the principal architect generating an UNBIASED post-mortem audit report. "
            "You must base your scores on the objective facts provided, not your ego."
        )
        user = (
            "Generate an audit report with these fields:\n"
            "1. **Turns**: Estimate from the conversation history lengths.\n"
            "2. **Total Issues**: How many issues were tracked.\n"
            "3. **Resolved / Acknowledged / Open**: Counts by status.\n"
            "4. **Fix Rate**: (resolved + acknowledged) / total as percentage.\n"
            "5. **Critic Hallucinations**: Issues where YOU (Critic) were wrong.\n"
            "6. **Critic Score** (1-10): How precise were YOUR review comments?\n"
            "7. **Agent Score** (1-10): How well did the engineer execute fixes?\n"
            "8. **Token Efficiency** (1-10): Rate context cache utilization based on the "
            "FinOps data provided. High cache hit ratio = high score. No data = N/A.\n"
            "9. **Final Advice**: One sentence for the human team lead.\n\n"
            "SCORING RULE: The orchestrator has computed these objective facts:\n"
            f"{objective_stats}\n"
            "You MUST incorporate these facts into your scores. If the Agent won many "
            "debates against your hallucinations, penalize your Critic Score and give "
            "the Agent a high score. Be honest.\n\n"
            f"--- Final Issue State ---\n"
            f"{json.dumps(issue_threads, indent=2, ensure_ascii=False)}"
        )
        return self.client.chat(system=system, user=user)
