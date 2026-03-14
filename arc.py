#!/usr/bin/env python3
"""A.R.C. CLI — Adversarial Resolution Cycle."""

import argparse
import json
import random
import re
import subprocess
import sys
from pathlib import Path

from app.context import get_git_diff, get_whole_repo_context
from app.core.critic_agent import CriticAgent

RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"
DEFAULT_RUBRICS = [str(p) for p in RUBRIC_DIR.glob("*.yaml")]

MAX_TURNS = 3

BANNER = r"""
   ╔══════════════════════════════════════════╗
   ║     [A] >>> ( R ) <<< [C]               ║
   ║     {tagline:<37s}║
   ╚══════════════════════════════════════════╝
"""

TAGLINES = [
    "Adversarial Resolution Cycle",
    "Automated Refactoring Court",
    "Agent vs Repo vs Critic",
    "Arena of Relentless Code Review",
    "Arguments, Rebuttals, Convergence",
]

CLAUDE_PROMPT_TEMPLATE = """You are the Agent — a senior engineer in the A.R.C. (Adversarial Resolution Cycle).
Fix the code based on the open issues below.
Each issue has a history of debate between the Critic and you (Agent).
Read the full history of each issue carefully before acting.

Rules:
1. Fix what you can. Push back on what you cannot or disagree with.
2. Every reply MUST start with exactly one of these tags:
   - [FIXED] — you changed the code. Say what you did.
   - [NOT FIXED] — you cannot fix it (needs human decision). Say why.
   - [DISAGREE] — the Critic is wrong (hallucinated file/package, wrong assumption,
     intentional design choice). Give a clear, factual reason.
3. If you already disagreed in a prior round and the Critic re-opened the same issue,
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


def _banner():
    tagline = random.choice(TAGLINES)
    print(BANNER.format(tagline=tagline))


def main():
    parser = argparse.ArgumentParser(
        prog="arc",
        description="A.R.C. — Adversarial Resolution Cycle.",
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
        help="Enable Agent vs Critic loop with structured issue tracking",
    )
    parser.add_argument(
        "--max-turns", type=int, default=MAX_TURNS,
        help=f"Max rounds for --fix (default: {MAX_TURNS})",
    )
    parser.add_argument(
        "--strict", action="store_true", default=False,
        help="Strict mode: block re-filed issues on settled code locations (Double Jeopardy)",
    )
    args = parser.parse_args()

    repo_path = str(Path(args.repo).resolve())
    rubric_paths = DEFAULT_RUBRICS if args.rubric else None
    critic = CriticAgent(rubric_paths=rubric_paths)

    _banner()

    if not args.fix:
        # Single-shot review
        diff, repo_context = _build_context(args.scope, repo_path, turn=1)
        print("[Critic] Reviewing codebase...\n")
        review = critic.review(diff=diff, repo_context=repo_context)
        print(review)
        return

    # Blackboard Pattern: structured issue threads
    print(f"[A.R.C.] Loading the arena (max {args.max_turns} rounds)...\n")
    issue_threads: dict = {}

    for turn in range(1, args.max_turns + 1):
        # ── Critic's turn ──────────────────────────────────────
        print(f"{'=' * 60}")
        print(f"  ROUND {turn}/{args.max_turns}")
        print(f"{'=' * 60}")

        diff, repo_context = _build_context(args.scope, repo_path, turn)

        # Double Jeopardy: collect file_lines that are already settled
        seen_targets = {
            issue["file_line"]
            for issue in issue_threads.values()
            if issue["status"] in ("resolved", "acknowledged") and issue.get("file_line")
        }

        print("[Critic] Reviewing...")
        updates = critic.review_stateful(
            issue_threads=issue_threads,
            diff=diff,
            repo_context=repo_context,
            seen_targets=seen_targets,
        )

        # Merge updates (skip noise on already-closed issues)
        for uid, update in updates.items():
            target = update.get("file_line", "")

            # Double Jeopardy: re-filed issue on a settled code location (fuzzy ±3 lines)
            if uid not in issue_threads and _is_double_jeopardy(target, seen_targets):
                if args.strict:
                    print(f"  [blocked] {uid} ({target}) — Double Jeopardy: within blast radius of settled issue.")
                    continue
                else:
                    print(f"  [warning] {uid} ({target}) — re-filing near settled location.")

            if uid in issue_threads:
                old_status = issue_threads[uid]["status"]
                new_status = update.get("status", old_status)
                if old_status in ("resolved", "acknowledged") and new_status == old_status:
                    continue

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
            reply = update.get("reply", "")
            if reply:
                issue_threads[uid]["history"].append({
                    "role": "critic",
                    "content": reply,
                })

        # Scoreboard
        open_issues = {k: v for k, v in issue_threads.items() if v["status"] == "open"}
        resolved = {k: v for k, v in issue_threads.items() if v["status"] == "resolved"}
        acked = {k: v for k, v in issue_threads.items() if v["status"] == "acknowledged"}

        print(f"\n  Scoreboard: {len(open_issues)} open | {len(resolved)} resolved | {len(acked)} acknowledged")
        for uid, issue in open_issues.items():
            reply = issue["history"][-1]["content"] if issue["history"] else ""
            print(f"\n  [{uid}] {issue['severity'].upper()} {issue['file_line']}")
            print(f"  {reply}")

        # Convergence
        if not open_issues:
            print(f"\n[A.R.C.] All issues settled in round {turn}. Court adjourned.")
            break

        # Last turn
        if turn == args.max_turns:
            print(f"\n[A.R.C.] Round limit reached ({args.max_turns}). {len(open_issues)} issue(s) escalated to human arbitration.")
            break

        # ── Agent's turn ───────────────────────────────────────
        print(f"\n[Agent] Entering the arena (round {turn})...")
        claude_prompt = CLAUDE_PROMPT_TEMPLATE.format(
            open_issues=json.dumps(open_issues, indent=2, ensure_ascii=False),
        )

        try:
            proc = subprocess.Popen(
                ["claude", "-p", "-", "--allowedTools", "Read,Edit,Bash"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                cwd=repo_path,
                text=True,
            )
            proc.stdin.write(claude_prompt)
            proc.stdin.close()

            print("-" * 60)
            agent_lines = []
            for line in proc.stdout:
                print(line, end="", flush=True)
                agent_lines.append(line)
            print("-" * 60)

            proc.wait()
            agent_output = "".join(agent_lines)

            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, "claude")

            # Parse structured reply
            match = re.search(
                r"<audit_reply>\s*(\{.*?\})\s*</audit_reply>",
                agent_output,
                re.DOTALL,
            )
            if match:
                try:
                    replies = json.loads(match.group(1))
                    for uid, reply in replies.items():
                        if uid in issue_threads:
                            issue_threads[uid]["history"].append({
                                "role": "agent",
                                "content": reply,
                            })
                    print(f"[Agent] {len(replies)} responses logged.\n")
                except json.JSONDecodeError:
                    print("[Agent] Warning: malformed JSON in <audit_reply>.\n")
                    _fallback_agent_reply(issue_threads, open_issues, agent_output)
            else:
                print("[Agent] Warning: no <audit_reply> tag found.\n")
                _fallback_agent_reply(issue_threads, open_issues, agent_output)

        except FileNotFoundError:
            print("[A.R.C.] `claude` not found. Install: npm install -g @anthropic-ai/claude-code")
            break
        except subprocess.CalledProcessError as e:
            print(f"[A.R.C.] Agent crashed with code {e.returncode}")
            break

    # ── Battle Report ──────────────────────────────────────────

    # Compute objective stats before audit
    total = len(issue_threads)
    fixed = len([i for i in issue_threads.values() if i["status"] == "resolved"])
    acked = len([i for i in issue_threads.values() if i["status"] == "acknowledged"])
    open_count = len([i for i in issue_threads.values() if i["status"] == "open"])
    disagrees = sum(
        1 for i in issue_threads.values()
        for h in i["history"]
        if h["role"] == "agent" and "[DISAGREE]" in h["content"]
    )

    # Build objective stats string to force honest scoring
    objective_stats = (
        f"- Total issues: {total}\n"
        f"- Resolved: {fixed}, Acknowledged: {acked}, Open: {open_count}\n"
        f"- Agent [DISAGREE] pushbacks: {disagrees}\n"
    )
    if acked > 0:
        objective_stats += f"- Critic was wrong on {acked} issue(s) (acknowledged = Critic error).\n"
    if disagrees >= 5:
        objective_stats += "- The Agent overwhelmingly dominated the debates. The Critic was frequently incorrect.\n"

    print(f"\n{'=' * 60}")
    print("         A.R.C. Battle Report")
    print(f"{'=' * 60}")

    # Objective scoreboard first
    print(f"\n  [Objective Scoreboard]")
    print(f"  Issues    : {total} total | {fixed} fixed | {acked} acknowledged | {open_count} open")
    print(f"  Pushbacks : {disagrees} [DISAGREE] from Agent")
    if disagrees >= 2:
        print(f"  MVP       : Agent (won {disagrees} debates)")
    elif fixed > total // 2:
        print(f"  MVP       : Critic (found {total} issues, {fixed} fixed)")
    else:
        print(f"  MVP       : Draw")
    print(f"{'-' * 60}")

    # Critic's subjective audit second
    print("\n  [Critic's Audit]")
    audit = critic.audit(issue_threads, objective_stats=objective_stats)
    print(audit)
    print(f"{'=' * 60}")

    # Dump threads
    print("\n--- Final Issue State (JSON) ---")
    print(json.dumps(issue_threads, indent=2, ensure_ascii=False))


def _is_double_jeopardy(new_target: str, seen_targets: set[str], radius: int = 3) -> bool:
    """Fuzzy match file_line to prevent LLM from re-filing by tweaking line numbers."""
    if not new_target:
        return False

    def parse(t: str):
        parts = str(t).rsplit(":", 1)
        filepath = parts[0].strip()
        lines = [int(x) for x in re.findall(r"\d+", parts[1])] if len(parts) > 1 else []
        return filepath, lines

    new_f, new_l = parse(new_target)
    if not new_f:
        return False

    for seen in seen_targets:
        if not seen:
            continue
        seen_f, seen_l = parse(seen)
        if new_f != seen_f:
            continue
        # Same file, no line numbers on either side = file-level match
        if not new_l or not seen_l:
            return True
        # Both have line numbers — check within radius
        if any(abs(n - s) <= radius for n in new_l for s in seen_l):
            return True

    return False


def _fallback_agent_reply(issue_threads: dict, open_issues: dict, output: str) -> None:
    """When Agent doesn't provide structured reply, mark parse failure."""
    for uid in open_issues:
        issue_threads[uid]["history"].append({
            "role": "agent",
            "content": "[parse failed] No structured <audit_reply> returned.",
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
        print("\n[A.R.C.] Human intervened. Court adjourned.")
        sys.exit(0)
