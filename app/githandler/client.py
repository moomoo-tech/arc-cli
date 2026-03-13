"""GitHub API client wrapping PyGithub for PR interactions."""

from github import Github

from config.settings import settings


class GitHubClient:
    """Encapsulates GitHub API operations for code review workflows."""

    def __init__(self, token: str | None = None):
        self._gh = Github(token or settings.github_token)

    def get_pr_diff(self, repo_name: str, pr_number: int) -> str:
        """Fetch the unified diff for a pull request."""
        repo = self._gh.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        files = pr.get_files()
        diffs = []
        for f in files:
            if f.patch:
                diffs.append(f"--- {f.filename}\n{f.patch}")
        return "\n\n".join(diffs)

    def post_review_comments(
        self, repo_name: str, pr_number: int, comments: list[dict], commit_sha: str
    ) -> None:
        """Post review comments on a pull request."""
        repo = self._gh.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        commit = repo.get_commit(commit_sha)

        for comment in comments:
            pr.create_review_comment(
                body=comment["body"],
                commit=commit,
                path=comment["path"],
                line=comment["line"],
            )

    def post_review_summary(
        self, repo_name: str, pr_number: int, body: str
    ) -> None:
        """Post a general review comment (not line-specific) on a PR."""
        repo = self._gh.get_repo(repo_name)
        issue = repo.get_issue(pr_number)
        issue.create_comment(body)
