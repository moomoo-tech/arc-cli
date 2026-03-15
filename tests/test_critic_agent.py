"""Tests for CriticAgent: stateful review, JSON parsing, Double Jeopardy, FinOps."""

import json
from unittest.mock import patch

import pytest

from app.core.critic_agent import CriticAgent
from app.llm.mock_client import MockClient


@pytest.fixture
def mock_client():
    client = MockClient()
    with patch("app.core.critic_agent.create_client", return_value=client):
        yield client


# ── review_stateful: JSON parsing ─────────────────────────────────


class TestStatefulJsonParsing:
    """review_stateful must extract JSON from various LLM output formats."""

    def test_clean_json(self, mock_client):
        mock_client.response = json.dumps({
            "ISSUE-1": {"status": "open", "file": "foo.py", "approx_line": 10,
                        "snippet": "x = 1", "severity": "error", "reply": "bug"}
        })
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads={}, repo_context="code")
        assert "ISSUE-1" in result
        assert result["ISSUE-1"]["status"] == "open"

    def test_json_in_markdown_fences(self, mock_client):
        mock_client.response = '```json\n{"ISSUE-1": {"status": "open", "file": "a.py", "approx_line": 1, "snippet": "x", "severity": "error", "reply": "x"}}\n```'
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads={}, repo_context="code")
        assert "ISSUE-1" in result

    def test_json_with_surrounding_text(self, mock_client):
        mock_client.response = 'Here is my review:\n{"ISSUE-1": {"status": "open", "file": "a.py", "approx_line": 1, "snippet": "x", "severity": "error", "reply": "x"}}\nDone.'
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads={}, repo_context="code")
        assert "ISSUE-1" in result

    def test_no_json_returns_empty(self, mock_client):
        mock_client.response = "No issues found, everything looks great!"
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads={}, repo_context="code")
        assert result == {}

    def test_invalid_json_returns_empty(self, mock_client):
        mock_client.response = '{"ISSUE-1": {broken json'
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads={}, repo_context="code")
        assert result == {}


# ── review_stateful: closed issue filtering ────────────────────────


class TestClosedIssueFilter:
    """review_stateful must drop echoed closed issues and block zombies."""

    def _make_thread(self, status):
        return {"status": status, "file": "a.py", "approx_line": 1,
                "snippet": "x", "severity": "error", "history": []}

    def test_resolved_echo_dropped(self, mock_client):
        threads = {"ISSUE-1": self._make_thread("resolved")}
        mock_client.response = json.dumps({
            "ISSUE-1": {"status": "resolved", "file": "a.py", "approx_line": 1,
                        "snippet": "x", "severity": "error", "reply": "still resolved"},
        })
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads=threads, repo_context="code")
        assert "ISSUE-1" not in result

    def test_acknowledged_echo_dropped(self, mock_client):
        threads = {"ISSUE-2": self._make_thread("acknowledged")}
        mock_client.response = json.dumps({
            "ISSUE-2": {"status": "acknowledged", "file": "b.py", "approx_line": 5,
                        "snippet": "y", "severity": "warning", "reply": "yep"},
        })
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads=threads, repo_context="code")
        assert "ISSUE-2" not in result

    def test_zombie_reopen_blocked(self, mock_client):
        """Once closed, Gemini cannot re-open — absolute lock."""
        threads = {"ISSUE-1": self._make_thread("resolved")}
        mock_client.response = json.dumps({
            "ISSUE-1": {"status": "open", "file": "a.py", "approx_line": 1,
                        "snippet": "x", "severity": "error", "reply": "fix was wrong"},
        })
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads=threads, repo_context="code")
        assert "ISSUE-1" not in result

    def test_new_issue_passes_through(self, mock_client):
        threads = {"ISSUE-1": self._make_thread("resolved")}
        mock_client.response = json.dumps({
            "ISSUE-2": {"status": "open", "file": "c.py", "approx_line": 20,
                        "snippet": "z", "severity": "warning", "reply": "new bug"},
        })
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads=threads, repo_context="code")
        assert "ISSUE-2" in result


# ── review_stateful: seen_targets in prompt ────────────────────────


class TestSeenTargetsPrompt:
    """review_stateful should include settled locations in the prompt."""

    def test_seen_targets_in_prompt(self, mock_client):
        mock_client.response = "{}"
        targets = [
            {"file": "foo.py", "approx_line": 10, "snippet": "x = 1"},
            {"file": "bar.py", "approx_line": 20, "snippet": "y = 2"},
        ]
        agent = CriticAgent()
        agent.review_stateful(issue_threads={}, repo_context="code", seen_targets=targets)
        assert "## Settled Locations (Double Jeopardy)" in mock_client.last_user
        assert "foo.py:~10" in mock_client.last_user
        assert "bar.py:~20" in mock_client.last_user

    def test_no_seen_targets_no_section(self, mock_client):
        mock_client.response = "{}"
        agent = CriticAgent()
        agent.review_stateful(issue_threads={}, repo_context="code", seen_targets=None)
        assert "Settled Locations" not in mock_client.last_user

    def test_empty_seen_targets_no_section(self, mock_client):
        mock_client.response = "{}"
        agent = CriticAgent()
        agent.review_stateful(issue_threads={}, repo_context="code", seen_targets=[])
        assert "Settled Locations" not in mock_client.last_user


# ── review_stateful: prompt content ────────────────────────────────


class TestStatefulPromptContent:
    """review_stateful should include issue threads, diff, and repo in prompt."""

    def test_first_review_says_none_yet(self, mock_client):
        mock_client.response = "{}"
        agent = CriticAgent()
        agent.review_stateful(issue_threads={}, repo_context="code")
        assert "None yet. This is the first review." in mock_client.last_user

    def test_existing_threads_in_prompt(self, mock_client):
        mock_client.response = "{}"
        threads = {"ISSUE-1": {"status": "open", "file": "x.py", "approx_line": 1,
                                "snippet": "bad code", "severity": "error", "history": []}}
        agent = CriticAgent()
        agent.review_stateful(issue_threads=threads, repo_context="code")
        assert "ISSUE-1" in mock_client.last_user
        assert "x.py" in mock_client.last_user

    def test_diff_in_prompt(self, mock_client):
        mock_client.response = "{}"
        agent = CriticAgent()
        agent.review_stateful(issue_threads={}, diff="--- a/f.py\n+new line")
        assert "## Current Changes (Git Diff)" in mock_client.last_user
        assert "+new line" in mock_client.last_user

    def test_repo_context_in_prompt(self, mock_client):
        mock_client.response = "{}"
        agent = CriticAgent()
        agent.review_stateful(issue_threads={}, repo_context="full repo here")
        assert "## Full Codebase" in mock_client.last_user
        assert "full repo here" in mock_client.last_user


# Double Jeopardy tests live in tests/test_utils.py (canonical location)


# ── Token tracking (FinOps) ───────────────────────────────────────


class TestTokenTracking:
    """GeminiClient should track token usage."""

    def test_gemini_client_has_counters(self):
        from app.llm.gemini_client import GeminiClient
        # Can't instantiate without API key, but check class has the attrs
        import inspect
        source = inspect.getsource(GeminiClient.__init__)
        assert "tokens_in" in source
        assert "tokens_out" in source
        assert "tokens_cached" in source
