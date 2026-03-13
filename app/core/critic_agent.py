"""Core critic agent: assembles prompts, calls LLM, and produces review comments."""

import json
import re

import anthropic

from app.core.rubric_parser import RubricParser
from config.settings import settings

SYSTEM_PROMPT = """You are A.R.C. (Agent Review Critic), a ruthless code review agent.
You exist solely to critique — you never write feature code.

Your job:
1. Review the diff against the provided rubric rules.
2. For each violation found, output a structured review comment.
3. If the code is clean, say so briefly.

Output format — return a JSON array of objects, each with:
- "path": the file path from the diff header
- "line": the line number in the new file where the issue is (best guess from diff context)
- "body": your review comment in Markdown. Be specific, cite the rule, suggest a fix direction.
- "severity": one of "critical", "error", "warning", "info"

If no issues found, return an empty array: []

Rules:
- Only flag real violations, not style nitpicks unless a rubric rule covers it.
- Be concise and actionable. No fluff.
- Include the rule name in each comment body, e.g. "[no-bare-except] ..."
"""


class CriticAgent:
    """A.R.C. brain — reviews code diffs against architectural rubrics."""

    def __init__(self, rubric_paths: list[str] | None = None):
        self.parser = RubricParser()
        self.rubrics = self.parser.load(rubric_paths or [])
        self.client = anthropic.Anthropic(api_key=settings.llm_api_key)

    async def review(self, diff: str, context: dict | None = None) -> list[dict]:
        """Review a code diff and return a list of review comments.

        Args:
            diff: The unified diff string to review.
            context: Optional metadata (repo, PR number, file paths, etc.).

        Returns:
            A list of comment dicts with keys: path, line, body, severity.
        """
        user_prompt = self._build_prompt(diff, context)

        response = self.client.messages.create(
            model=settings.llm_model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        return self._parse_response(response.content[0].text)

    def _build_prompt(self, diff: str, context: dict | None = None) -> str:
        """Assemble the user prompt from rubrics and the diff."""
        rubric_text = self.parser.format_rules(self.rubrics)

        parts = [
            "## Rubric Rules\n",
            rubric_text,
            "\n\n## Diff to Review\n",
            diff,
        ]

        if context:
            parts.insert(0, f"PR #{context.get('pr_number', '?')} in {context.get('repo', '?')}\n\n")

        return "".join(parts)

    def _parse_response(self, text: str) -> list[dict]:
        """Parse the LLM response into structured comment dicts."""
        # Extract JSON array from response (may be wrapped in markdown fences)
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []

        try:
            comments = json.loads(match.group())
        except json.JSONDecodeError:
            return []

        # Validate and normalize each comment
        valid = []
        for c in comments:
            if not isinstance(c, dict):
                continue
            if "body" not in c:
                continue
            valid.append({
                "path": c.get("path", ""),
                "line": c.get("line", 1),
                "body": c["body"],
                "severity": c.get("severity", "warning"),
            })

        return valid
