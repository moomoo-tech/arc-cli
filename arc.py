#!/usr/bin/env python3
"""A.R.C. CLI — Agent Review Critic (Blackboard Pattern)."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from app.context import get_git_diff, get_whole_repo_context
from app.core.critic_agent import CriticAgent

RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"
DEFAULT_RUBRICS = [str(p) for p in RUBRIC_DIR.glob("*.yaml")]

MAX_TURNS = 3

CLAUDE_PROMPT_TEMPLATE = """You are a senior engineer. Fix the code based on the open issues below.
Each issue has a history of comments between the architect (critic) and you (actor).
Read the full history of each issue carefully before acting.

Rules:
1. Fix what you can. Push back on what you cannot or disagree with.
2. Every reply MUST start with exactly one of these tags:
   - [FIXED] — you changed the code. Say what you did.
   - [NOT FIXED] — you cannot fix it (needs human decision). Say why.
   - [DISAGREE] — the architect is wrong (hallucinated file/package, wrong assumption,
     intentional design choice). Give a clear, factual reason.
3. If you already disagreed in a prior turn and the architect re-opened the same issue,
   hold your ground. Repeat your reasoning with evidence.

After all fixes, you MUST end your response with an <audit_reply> XML tag containing
a JSON object keyed by ISSUE-ID:

<audit_reply>
{{
  "ISSUE-1": "[FIXED] Changed to use os.getenv()",
  "ISSUE-2": "[DISAGREE] google-genai is the correct package. genai.Client() is the valid API.",
  "ISSUE-3": "[NOT FIXED] Needs human decision on auth provider."
}}
</audit_reply>

--- Open Issues ---
{open_issues}"""


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
        help="Enable Actor-Critic loop with structured issue tracking",
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
        # Single-shot free-form review
        diff, repo_context = _build_context(args.scope, repo_path, turn=1)
        print("[A.R.C.] Running review...\n")
        review = agent.review(diff=diff, repo_context=repo_context)
        print("=" * 60)
        print(review)
        print("=" * 60)
        return

    # Blackboard Pattern: structured issue threads
    print(f"[A.R.C.] Starting Actor-Critic loop (max {args.max_turns} turns)...\n")
    issue_threads: dict = {}

    for turn in range(1, args.max_turns + 1):
        print(f"--- Turn {turn}/{args.max_turns} ---")

        # Re-read context each turn (actor may have changed files)
        diff, repo_context = _build_context(args.scope, repo_path, turn)

        # Critic: review and return structured JSON updates
        print("[Critic] Reviewing...")
        updates = agent.review_stateful(
            issue_threads=issue_threads,
            diff=diff,
            repo_context=repo_context,
        )

        # Merge updates into issue_threads
        for uid, update in updates.items():
            if uid not in issue_threads:
                issue_threads[uid] = {
                    "status": "open",
                    "file_line": update.get("file_line", "unknown"),
                    "severity": update.get("severity", "warning"),
                    "history": [],
                }
            issue_threads[uid]["status"] = update.get("status", "open")
            if update.get("file_line"):
                issue_threads[uid]["file_line"] = update["file_line"]
            if update.get("severity"):
                issue_threads[uid]["severity"] = update["severity"]
            issue_threads[uid]["history"].append({
                "role": "critic",
                "content": update.get("reply", ""),
            })

        # Print current state
        open_issues = {k: v for k, v in issue_threads.items() if v["status"] == "open"}
        resolved = {k: v for k, v in issue_threads.items() if v["status"] == "resolved"}
        acked = {k: v for k, v in issue_threads.items() if v["status"] == "acknowledged"}

        print(f"  Open: {len(open_issues)} | Resolved: {len(resolved)} | Acknowledged: {len(acked)}")
        for uid, issue in open_issues.items():
            print(f"  [{uid}] {issue['severity'].upper()} {issue['file_line']}: {issue['history'][-1]['content'][:80]}")

        # Convergence: no open issues
        if not open_issues:
            print(f"\n[A.R.C.] PASS — converged on turn {turn}. All issues resolved or acknowledged.")
            break

        # Last turn — no point invoking actor
        if turn == args.max_turns:
            print(f"\n[A.R.C.] Reached max turns ({args.max_turns}). {len(open_issues)} issue(s) still open.")
            break

        # Actor: send only open issues to Claude
        print(f"\n[Actor] Invoking Claude Code (turn {turn})...")
        claude_prompt = CLAUDE_PROMPT_TEMPLATE.format(
            open_issues=json.dumps(open_issues, indent=2, ensure_ascii=False),
        )

        try:
            result = subprocess.run(
                ["claude", "-p", "-", "--allowedTools", "Read,Edit,Bash"],
                input=claude_prompt,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            actor_output = result.stdout

            # Print Claude's full response
            print("=" * 60)
            print(actor_output)
            print("=" * 60)

            # Extract structured reply from <audit_reply> tags
            match = re.search(
                r"<audit_reply>\s*(\{.*?\})\s*</audit_reply>",
                actor_output,
                re.DOTALL,
            )
            if match:
                try:
                    replies = json.loads(match.group(1))
                    for uid, reply in replies.items():
                        if uid in issue_threads:
                            issue_threads[uid]["history"].append({
                                "role": "actor",
                                "content": reply,
                            })
                    print(f"[Actor] Parsed {len(replies)} structured replies.\n")
                except json.JSONDecodeError:
                    print("[Actor] Warning: invalid JSON in <audit_reply>. Using fallback.\n")
                    _fallback_actor_reply(issue_threads, open_issues, actor_output)
            else:
                print("[Actor] Warning: no <audit_reply> tag found. Using fallback.\n")
                _fallback_actor_reply(issue_threads, open_issues, actor_output)

        except FileNotFoundError:
            print("[A.R.C.] `claude` not found. Install: npm install -g @anthropic-ai/claude-code")
            break
        except subprocess.CalledProcessError as e:
            print(f"[A.R.C.] Claude exited with code {e.returncode}")
            break

    # Audit report
    print("\n[A.R.C.] Generating audit report...\n")
    audit = agent.audit(issue_threads)

    print("=" * 60)
    print("         A.R.C. Audit Report")
    print("=" * 60)
    print(audit)
    print("=" * 60)

    # Dump final state
    print("\n--- Final Issue State (JSON) ---")
    print(json.dumps(issue_threads, indent=2, ensure_ascii=False))


def _fallback_actor_reply(issue_threads: dict, open_issues: dict, output: str) -> None:
    """When Claude doesn't provide structured reply, stuff raw output into all open issues."""
    snippet = output[-500:] if len(output) > 500 else output
    for uid in open_issues:
        issue_threads[uid]["history"].append({
            "role": "actor",
            "content": f"[unstructured response] {snippet}",
        })


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
