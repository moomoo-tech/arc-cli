"""Tests for arc CLI flags: --scope (diff, diff+repo, repo) and --rubric."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.critic_agent import CriticAgent
from app.llm.mock_client import MockClient


@pytest.fixture
def mock_client():
    """Create a MockClient and patch create_client to return it."""
    client = MockClient()
    with patch("app.core.critic_agent.create_client", return_value=client):
        yield client


@pytest.fixture
def sample_repo(tmp_path):
    """Create a tiny git repo with one file and a dirty diff."""
    # Init repo
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, capture_output=True,
    )

    # Create and commit a file
    hello = tmp_path / "hello.py"
    hello.write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, capture_output=True,
    )

    # Make a dirty change (unstaged)
    hello.write_text("print('hello world')\n")
    return tmp_path


# ── Scope tests ────────────────────────────────────────────────────


class TestScopeRepo:
    """--scope repo: sends full repo context, no diff."""

    def test_sends_repo_context(self, mock_client):
        agent = CriticAgent()
        result = agent.review(diff=None, repo_context="file content here")
        assert mock_client.call_count == 1
        assert "## Full Codebase" in mock_client.last_user
        assert "file content here" in mock_client.last_user
        assert "Git Diff" not in mock_client.last_user

    def test_no_diff_section(self, mock_client):
        agent = CriticAgent()
        agent.review(diff=None, repo_context="code")
        assert "## Current Changes" not in mock_client.last_user


class TestScopeDiff:
    """--scope diff: sends only the diff, no repo context."""

    def test_sends_diff_only(self, mock_client):
        agent = CriticAgent()
        result = agent.review(diff="--- a/foo.py\n+bar", repo_context=None)
        assert mock_client.call_count == 1
        assert "## Current Changes (Git Diff)" in mock_client.last_user
        assert "--- a/foo.py" in mock_client.last_user
        assert "## Full Codebase" not in mock_client.last_user

    def test_no_repo_section(self, mock_client):
        agent = CriticAgent()
        agent.review(diff="some diff", repo_context=None)
        assert "## Full Codebase" not in mock_client.last_user


class TestScopeDiffRepo:
    """--scope diff+repo: sends both diff and full repo."""

    def test_sends_both(self, mock_client):
        agent = CriticAgent()
        result = agent.review(diff="the diff", repo_context="the repo")
        assert mock_client.call_count == 1
        assert "## Current Changes (Git Diff)" in mock_client.last_user
        assert "the diff" in mock_client.last_user
        assert "## Full Codebase" in mock_client.last_user
        assert "the repo" in mock_client.last_user


# ── Rubric tests ───────────────────────────────────────────────────


RUBRIC_DIR = Path(__file__).resolve().parent.parent / "rubrics"
DEFAULT_RUBRICS = [str(p) for p in RUBRIC_DIR.glob("*.yaml")]


class TestRubricOff:
    """--rubric not set (default): no rubric rules in prompt."""

    def test_no_rubric_section(self, mock_client):
        agent = CriticAgent(rubric_paths=None)
        agent.review(repo_context="code")
        assert "## Rubric Rules" not in mock_client.last_user

    def test_no_rubric_empty_list(self, mock_client):
        agent = CriticAgent(rubric_paths=[])
        agent.review(repo_context="code")
        assert "## Rubric Rules" not in mock_client.last_user


class TestRubricOn:
    """--rubric flag set: rubric rules included in prompt."""

    def test_rubric_section_present(self, mock_client):
        agent = CriticAgent(rubric_paths=DEFAULT_RUBRICS)
        agent.review(repo_context="code")
        assert "## Rubric Rules" in mock_client.last_user

    def test_rubric_contains_rule_names(self, mock_client):
        agent = CriticAgent(rubric_paths=DEFAULT_RUBRICS)
        agent.review(repo_context="code")
        # Rules from bundled rubrics should appear
        assert "no-hardcoded-secrets" in mock_client.last_user
        assert "no-bare-except" in mock_client.last_user


# ── Combination tests ──────────────────────────────────────────────


class TestCombinations:
    """Test scope + rubric flag combinations."""

    def test_diff_with_rubric(self, mock_client):
        agent = CriticAgent(rubric_paths=DEFAULT_RUBRICS)
        agent.review(diff="my diff", repo_context=None)
        assert "## Rubric Rules" in mock_client.last_user
        assert "## Current Changes (Git Diff)" in mock_client.last_user
        assert "## Full Codebase" not in mock_client.last_user

    def test_repo_without_rubric(self, mock_client):
        agent = CriticAgent(rubric_paths=None)
        agent.review(diff=None, repo_context="all the code")
        assert "## Rubric Rules" not in mock_client.last_user
        assert "## Full Codebase" in mock_client.last_user

    def test_diff_repo_with_rubric(self, mock_client):
        agent = CriticAgent(rubric_paths=DEFAULT_RUBRICS)
        agent.review(diff="diff here", repo_context="repo here")
        assert "## Rubric Rules" in mock_client.last_user
        assert "## Current Changes (Git Diff)" in mock_client.last_user
        assert "## Full Codebase" in mock_client.last_user


# ── MockClient sanity ──────────────────────────────────────────────


class TestMockClient:
    """Verify MockClient itself works correctly."""

    def test_records_calls(self):
        c = MockClient()
        result = c.chat(system="sys", user="usr")
        assert result == "LGTM — no issues found."
        assert c.last_system == "sys"
        assert c.last_user == "usr"
        assert c.call_count == 1

    def test_custom_response(self):
        c = MockClient()
        c.response = "found 3 bugs"
        assert c.chat(system="", user="") == "found 3 bugs"
        assert c.call_count == 1

    def test_multiple_calls_increment_count(self):
        c = MockClient()
        c.chat(system="", user="")
        c.chat(system="", user="")
        assert c.call_count == 2
