"""Tests for CriticAgent: stateful review, JSON parsing, and Double Jeopardy."""

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
            "ISSUE-1": {"status": "open", "file_line": "foo.py:10", "severity": "error", "reply": "bug"}
        })
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads={}, repo_context="code")
        assert "ISSUE-1" in result
        assert result["ISSUE-1"]["status"] == "open"

    def test_json_in_markdown_fences(self, mock_client):
        mock_client.response = '```json\n{"ISSUE-1": {"status": "open", "file_line": "a.py:1", "severity": "error", "reply": "x"}}\n```'
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads={}, repo_context="code")
        assert "ISSUE-1" in result

    def test_json_with_surrounding_text(self, mock_client):
        mock_client.response = 'Here is my review:\n{"ISSUE-1": {"status": "open", "file_line": "a.py:1", "severity": "error", "reply": "x"}}\nDone.'
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
    """review_stateful must drop echoed closed issues."""

    def test_resolved_echo_dropped(self, mock_client):
        threads = {
            "ISSUE-1": {"status": "resolved", "file_line": "a.py:1", "severity": "error", "history": []},
        }
        mock_client.response = json.dumps({
            "ISSUE-1": {"status": "resolved", "file_line": "a.py:1", "severity": "error", "reply": "still resolved"},
        })
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads=threads, repo_context="code")
        assert "ISSUE-1" not in result

    def test_acknowledged_echo_dropped(self, mock_client):
        threads = {
            "ISSUE-2": {"status": "acknowledged", "file_line": "b.py:5", "severity": "warning", "history": []},
        }
        mock_client.response = json.dumps({
            "ISSUE-2": {"status": "acknowledged", "file_line": "b.py:5", "severity": "warning", "reply": "yep"},
        })
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads=threads, repo_context="code")
        assert "ISSUE-2" not in result

    def test_zombie_reopen_blocked(self, mock_client):
        """Once closed, Gemini cannot re-open — absolute lock."""
        threads = {
            "ISSUE-1": {"status": "resolved", "file_line": "a.py:1", "severity": "error", "history": []},
        }
        mock_client.response = json.dumps({
            "ISSUE-1": {"status": "open", "file_line": "a.py:1", "severity": "error", "reply": "fix was wrong"},
        })
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads=threads, repo_context="code")
        assert "ISSUE-1" not in result  # blocked by absolute lock

    def test_new_issue_passes_through(self, mock_client):
        threads = {
            "ISSUE-1": {"status": "resolved", "file_line": "a.py:1", "severity": "error", "history": []},
        }
        mock_client.response = json.dumps({
            "ISSUE-2": {"status": "open", "file_line": "c.py:20", "severity": "warning", "reply": "new bug"},
        })
        agent = CriticAgent()
        result = agent.review_stateful(issue_threads=threads, repo_context="code")
        assert "ISSUE-2" in result


# ── review_stateful: seen_targets in prompt ────────────────────────


class TestSeenTargetsPrompt:
    """review_stateful should include settled locations in the prompt."""

    def test_seen_targets_in_prompt(self, mock_client):
        mock_client.response = "{}"
        agent = CriticAgent()
        agent.review_stateful(
            issue_threads={},
            repo_context="code",
            seen_targets={"foo.py:10", "bar.py:20"},
        )
        assert "## Settled Locations (Double Jeopardy)" in mock_client.last_user
        assert "foo.py:10" in mock_client.last_user
        assert "bar.py:20" in mock_client.last_user

    def test_no_seen_targets_no_section(self, mock_client):
        mock_client.response = "{}"
        agent = CriticAgent()
        agent.review_stateful(issue_threads={}, repo_context="code", seen_targets=None)
        assert "Settled Locations" not in mock_client.last_user

    def test_empty_seen_targets_no_section(self, mock_client):
        mock_client.response = "{}"
        agent = CriticAgent()
        agent.review_stateful(issue_threads={}, repo_context="code", seen_targets=set())
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
        threads = {"ISSUE-1": {"status": "open", "file_line": "x.py:1", "severity": "error", "history": []}}
        agent = CriticAgent()
        agent.review_stateful(issue_threads=threads, repo_context="code")
        assert "ISSUE-1" in mock_client.last_user
        assert "x.py:1" in mock_client.last_user

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


# ── Double Jeopardy: fuzzy matching ───────────────────────────────


class TestDoubleJeopardy:
    """Test _is_double_jeopardy fuzzy line matching from arc.py."""

    def setup_method(self):
        from arc import _is_double_jeopardy
        self.check = _is_double_jeopardy

    def test_exact_match(self):
        assert self.check("foo.py:10", {"foo.py:10"})

    def test_within_radius(self):
        assert self.check("foo.py:12", {"foo.py:10"})  # diff = 2, radius = 3

    def test_outside_radius(self):
        assert not self.check("foo.py:20", {"foo.py:10"})  # diff = 10

    def test_different_file(self):
        assert not self.check("bar.py:10", {"foo.py:10"})

    def test_file_only_vs_file_with_line(self):
        assert self.check("foo.py", {"foo.py:10"})  # no line = whole file

    def test_file_with_line_vs_file_only(self):
        assert self.check("foo.py:5", {"foo.py"})

    def test_range_line_numbers(self):
        assert self.check("req.txt:4-5", {"req.txt:5"})  # line 5 matches exactly

    def test_empty_target(self):
        assert not self.check("", {"foo.py:10"})

    def test_empty_seen(self):
        assert not self.check("foo.py:10", set())

    def test_no_match_in_seen(self):
        assert not self.check("foo.py:10", {"bar.py:1", "baz.py:99"})
