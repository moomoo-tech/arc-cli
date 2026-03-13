"""FastAPI gateway layer for receiving and validating GitHub webhooks."""

import asyncio
import hashlib
import hmac
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Header, BackgroundTasks

from config.settings import settings
from app.core.critic_agent import CriticAgent
from app.githandler.client import GitHubClient

app = FastAPI(title="A.R.C. - Agent Review Critic")

# Load default rubrics from rubrics/ directory
RUBRIC_DIR = Path(__file__).resolve().parent.parent.parent / "rubrics"
DEFAULT_RUBRICS = [str(p) for p in RUBRIC_DIR.glob("*.yaml")]


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature (HMAC-SHA256)."""
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def run_review(repo_name: str, pr_number: int, commit_sha: str) -> None:
    """Background task: pull diff, run critic, post comments."""
    print(f"[A.R.C.] Reviewing PR #{pr_number} in {repo_name}")

    gh = GitHubClient()
    critic = CriticAgent(rubric_paths=DEFAULT_RUBRICS)

    try:
        diff = gh.get_pr_diff(repo_name, pr_number)
        if not diff:
            print(f"[A.R.C.] PR #{pr_number} has no diff, skipping.")
            return

        context = {"repo": repo_name, "pr_number": pr_number}
        comments = await critic.review(diff, context)

        if comments:
            # Post line-level comments
            gh.post_review_comments(repo_name, pr_number, comments, commit_sha)

            # Post summary
            severity_counts = {}
            for c in comments:
                s = c["severity"]
                severity_counts[s] = severity_counts.get(s, 0) + 1
            summary_parts = [f"**A.R.C. Review** — {len(comments)} issue(s) found\n"]
            for s, count in sorted(severity_counts.items()):
                emoji = {"critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🔵"}.get(s, "⚪")
                summary_parts.append(f"{emoji} {s}: {count}")
            gh.post_review_summary(repo_name, pr_number, "\n".join(summary_parts))
        else:
            gh.post_review_summary(
                repo_name, pr_number,
                "**A.R.C. Review** — ✅ No issues found. Code looks clean."
            )

        print(f"[A.R.C.] Review complete: {len(comments)} comment(s) posted.")

    except Exception as e:
        print(f"[A.R.C.] Review failed for PR #{pr_number}: {e}")
        try:
            gh.post_review_summary(
                repo_name, pr_number,
                f"**A.R.C. Review** — ⚠️ Review failed: {e}"
            )
        except Exception:
            pass


@app.post("/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    """Receive GitHub webhook events and dispatch to the critic agent."""
    payload = await request.body()

    if settings.github_webhook_secret and x_hub_signature_256:
        if not verify_signature(payload, x_hub_signature_256, settings.github_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    data = await request.json()
    action = data.get("action")

    if action not in ("opened", "synchronize"):
        return {"status": "ignored", "action": action}

    repo_name = data["repository"]["full_name"]
    pr_number = data["pull_request"]["number"]
    commit_sha = data["pull_request"]["head"]["sha"]

    # Dispatch review as background task — respond to GitHub immediately
    background_tasks.add_task(run_review, repo_name, pr_number, commit_sha)

    return {
        "status": "dispatched",
        "pr": pr_number,
        "repo": repo_name,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
