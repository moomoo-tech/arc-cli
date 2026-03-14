#!/usr/bin/env python3
"""A.R.C. CLI — Agent Review Critic (Actor-Critic Loop with Audit)."""

import argparse
import subprocess
import sys
from pathlib import Path

from app.context import get_git_diff, get_whole_repo_context
from app.core.critic_agent import CriticAgent

RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"
DEFAULT_RUBRICS = [str(p) for p in RUBRIC_DIR.glob("*.yaml")]

MAX_TURNS = 3

CLAUDE_PROMPT_TEMPLATE = (
    "You are a senior engineer. "
    "Fix the local code based strictly on the following review report. "
    "Do not add anything beyond what the report asks for.\n\n"
    "You MUST respond to EVERY comment in the review, one by one, using this format:\n"
    "- [FIXED] <file:line> — what you changed\n"
    "- [NOT FIXED] <file:line> — why you could not fix it (e.g. needs human decision)\n"
    "- [DISAGREE] <file:line> — why the reviewer is wrong (hallucination, incorrect assumption)\n\n"
    "After all comments, add:\n"
    "[Reviewer Score: X/10] followed by a short reason.\n\n"
    "--- Review Report ---\n{review}"
)


def main():
    parser = argparse.ArgumentParser(
        prog="arc",
        description="A.R.C. — Agent Review Critic.",
    )
    parser.add_argument(
        "repo", nargs="?", default=".",
        help="Path to the repo to review (default: current directory)",
    )
    parser.add_argument(
        "--scope", choices=["diff", "diff+repo", "repo"], default="repo",
        help="Review scope (default: repo)",
    )
    parser.add_argument(
        "--rubric", action="store_true", default=False,
        help="Enable rubric rules (default: off)",
    )
    parser.add_argument(
        "--fix", action="store_true", default=False,
        help="Enable Actor-Critic loop: Gemini reviews, Claude fixes",
    )
    parser.add_argument(
        "--max-turns", type=int, default=MAX_TURNS,
        help=f"Max loop iterations for --fix (default: {MAX_TURNS})",
    )
    args = parser.parse_args()

    repo_path = str(Path(args.repo).resolve())
    rubric_paths = DEFAULT_RUBRICS if args.rubric else None
    agent = CriticAgent(rubric_paths=rubric_paths)

    if not args.fix:
        # Single-shot review
        diff, repo_context = _build_context(args.scope, repo_path, turn=1)
        print("[A.R.C.] Running review...\n")
        review = agent.review(diff=diff, repo_context=repo_context)
        print("=" * 60)
        print(review)
        print("=" * 60)
        return

    # Actor-Critic Loop with session ledger
    print(f"[A.R.C.] Starting Actor-Critic loop (max {args.max_turns} turns)...\n")
    session_log: list[str] = []
    converged = False

    for turn in range(1, args.max_turns + 1):
        print(f"--- Turn {turn}/{args.max_turns} ---")

        # Re-read context each turn
        diff, repo_context = _build_context(args.scope, repo_path, turn)

        # Critic
        print("[Critic] Reviewing...")
        review = agent.review(diff=diff, repo_context=repo_context)
        session_log.append(f"[Turn {turn} - Critic Review]\n{review}")

        # Convergence check
        if "[PASS]" in review:
            print(f"\n[A.R.C.] PASS — converged on turn {turn}.")
            print("=" * 60)
            print(review)
            print("=" * 60)
            converged = True
            break

        print("=" * 60)
        print(review)
        print("=" * 60)

        # Last turn — no point invoking actor
        if turn == args.max_turns:
            print(f"\n[A.R.C.] Reached max turns ({args.max_turns}). Human takeover needed.")
            break

        # Actor
        print(f"\n[Actor] Invoking Claude Code (turn {turn})...")
        claude_prompt = CLAUDE_PROMPT_TEMPLATE.format(review=review)

        try:
            result = subprocess.run(
                ["claude", "-p", claude_prompt, "--allowedTools", "Read,Edit,Bash"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            actor_output = result.stdout
            session_log.append(f"[Turn {turn} - Actor Execution]\n{actor_output}")
            agent.add_actor_feedback(actor_output)
            print(f"[Actor] Turn {turn} fixes applied. Re-reviewing...\n")
        except FileNotFoundError:
            session_log.append(f"[Turn {turn} - Actor Error]\nclaude CLI not found")
            print("[A.R.C.] `claude` not found. Install: npm install -g @anthropic-ai/claude-code")
            break
        except subprocess.CalledProcessError as e:
            session_log.append(f"[Turn {turn} - Actor Error]\n{e.stderr}")
            print(f"[A.R.C.] Claude exited with code {e.returncode}")
            break

    # Audit report
    print("\n[A.R.C.] Generating audit report...\n")
    full_log = "\n\n".join(session_log)
    audit = agent.audit(full_log)

    print("=" * 60)
    print("         A.R.C. Audit Report")
    print("=" * 60)
    print(audit)
    print("=" * 60)


def _build_context(scope: str, repo_path: str, turn: int):
    """Gather diff and/or repo context based on scope."""
    diff = None
    repo_context = None

    if scope in ("diff", "diff+repo"):
        diff = get_git_diff(repo_path)
        if not diff and turn == 1:
            print("[A.R.C.] No changes detected. Nothing to review.")
            sys.exit(0)

    if scope in ("repo", "diff+repo"):
        repo_context = get_whole_repo_context(repo_path)

    return diff, repo_context


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[A.R.C.] Interrupted.")
        sys.exit(0)
