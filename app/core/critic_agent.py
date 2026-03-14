"""Critic agent: assembles context, calls LLM, returns review comments."""

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
- When all issues are resolved, you MUST output [PASS].
"""


class CriticAgent:
    """Calls LLM to review code. Returns review text."""

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
        """Review code based on whatever context is provided.

        Args:
            diff: Git diff string (optional).
            repo_context: Full repo contents (optional).

        Returns:
            Review text (Markdown).
        """
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

    def audit(self, session_log: str) -> str:
        """Generate a structured audit report from the full session log."""
        system = (
            "You are the principal architect generating a post-mortem audit report. "
            "Read the full pipeline log and produce a structured report."
        )
        user = (
            "Generate an audit report with these fields:\n"
            "1. **Turns**: How many review cycles were consumed.\n"
            "2. **Initial Issues**: How many issues the critic raised in turn 1.\n"
            "3. **Fixed / Remaining**: How many were fixed vs still open.\n"
            "4. **Fix Rate**: Percentage.\n"
            "5. **Invalid Suggestions**: Issues the actor could not execute "
            "(wrong line numbers, hallucinated files, over-engineering).\n"
            "6. **Critic Score** (architect rates the actor, 1-10): "
            "How precise were the code fixes?\n"
            "7. **Actor Score** (actor rates the architect, 1-10): "
            "Extract from the actor's self-reported score in the log.\n"
            "8. **Final Advice**: One sentence for the human team lead.\n\n"
            f"--- Session Log ---\n{session_log}"
        )
        return self.client.chat(system=system, user=user)
