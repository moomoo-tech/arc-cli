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
- File path and line number
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
   - [FIXED]: Verify the fix is correct. If so, set "status" to "resolved".
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

You MUST output ONLY a JSON object (no markdown fences, no extra text) like:
{
  "ISSUE-1": {
    "status": "resolved",
    "file_line": "app/auth.py:45",
    "severity": "critical",
    "reply": "Fix looks correct."
  },
  "ISSUE-2": {
    "status": "acknowledged",
    "file_line": "requirements.txt:5",
    "severity": "error",
    "reply": "Accepted. I was wrong about the package name. Ignoring this issue."
  },
  "ISSUE-3": {
    "status": "open",
    "file_line": "utils.py:10",
    "severity": "error",
    "reply": "Still catching bare Exception. Catch specific exceptions."
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
    ) -> dict:
        """Stateful review: takes issue threads dict, returns JSON updates.

        Args:
            issue_threads: Current state of all issues.
            diff: Git diff string (optional).
            repo_context: Full repo contents (optional).

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

        if diff:
            parts.append(f"## Current Changes (Git Diff)\n{diff}")

        if repo_context:
            parts.append(f"## Full Codebase\n{repo_context}")

        raw = self.client.chat(
            system=STATEFUL_SYSTEM_PROMPT,
            user="\n\n".join(parts),
        )

        # Extract JSON robustly (LLM may wrap in markdown fences)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            print(f"[Critic] Failed to parse JSON from response:\n{raw[:200]}")
            return {}

        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            print(f"[Critic] Invalid JSON in response:\n{raw[:200]}")
            return {}

    def audit(self, issue_threads: dict) -> str:
        """Generate audit report from the final issue threads state."""
        system = (
            "You are the principal architect generating a post-mortem audit report. "
            "Read the final issue state and produce a structured report."
        )
        user = (
            "Generate an audit report with these fields:\n"
            "1. **Turns**: Estimate from the conversation history lengths.\n"
            "2. **Total Issues**: How many issues were tracked.\n"
            "3. **Resolved / Acknowledged / Open**: Counts by status.\n"
            "4. **Fix Rate**: (resolved + acknowledged) / total as percentage.\n"
            "5. **Invalid Suggestions**: Issues acknowledged because the critic was wrong.\n"
            "6. **Critic Score** (1-10): How precise were the review comments?\n"
            "7. **Actor Score** (1-10): How well did the engineer execute fixes?\n"
            "8. **Final Advice**: One sentence for the human team lead.\n\n"
            f"--- Final Issue State ---\n"
            f"{json.dumps(issue_threads, indent=2, ensure_ascii=False)}"
        )
        return self.client.chat(system=system, user=user)
