#!/usr/bin/env python3
"""A.R.C. CLI — Adversarial Resolution Cycle."""

import argparse
import json
import random
import re
import subprocess
import sys
import threading
from pathlib import Path

from app.context import get_git_diff, get_whole_repo_context
from app.core.critic_agent import CriticAgent
from app.core.utils import is_double_jeopardy

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

LOCATION: Each issue has "file", "approx_line", and "snippet". Line numbers may have
shifted due to edits — use the "snippet" as your anchor to find the correct code.

Rules:
1. Fix what you can. Push back on what you cannot or disagree with.
2. Every reply MUST start with exactly one of these tags:
   - [FIXED] — you changed the code. Say what you did.
   - [NOT FIXED] — you cannot fix it (needs human decision). Say why.
   - [DISAGREE] — the Critic is wrong (hallucinated file/package, wrong assumption,
     intentional design choice). Give a clear, factual reason.
3. If you already disagreed in a prior round and the Critic re-opened the same issue,
   hold your ground. Repeat your reasoning with evidence.
4. QUOTE THE THREAD: In your reply, quote the Critic's main point to prove you are
   addressing the right issue.

CRITICAL OUTPUT FORMAT:
After all fixes, you MUST end your response with an <agent_reply> XML tag containing
a JSON object keyed by ISSUE-ID. Each value has "quote" and "reply":

<agent_reply>
{{
  "ISSUE-1": {{
    "quote": "Critic: [NEW] max_tokens default is 500_000",
    "reply": "[FIXED] Changed default to 16_384 across all clients."
  }},
  "ISSUE-2": {{
    "quote": "Critic: [REOPEN] genai.Client is not a valid API",
    "reply": "[DISAGREE] google-genai uses genai.Client(), not google-generativeai."
  }}
}}
</agent_reply>

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
        _print_finops(critic)
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

        # 3D Double Jeopardy: settled issues as list of dicts
        seen_targets = [
            issue for issue in issue_threads.values()
            if issue["status"] in ("resolved", "acknowledged")
        ]

        print("[Critic] Reviewing...")
        updates = critic.review_stateful(
            issue_threads=issue_threads,
            diff=diff,
            repo_context=repo_context,
            seen_targets=seen_targets if seen_targets else None,
        )

        # Merge updates
        for uid, update in updates.items():
            # 3D Double Jeopardy check (file + snippet + line radius)
            if uid not in issue_threads and is_double_jeopardy(update, seen_targets):
                if args.strict:
                    print(f"  [blocked] {uid} ({update.get('file')}:~{update.get('approx_line')}) — Double Jeopardy.")
                    continue
                else:
                    print(f"  [warning] {uid} ({update.get('file')}:~{update.get('approx_line')}) — re-filing near settled location.")

            if uid in issue_threads:
                old_status = issue_threads[uid]["status"]
                new_status = update.get("status", old_status)
                if old_status in ("resolved", "acknowledged") and new_status == old_status:
                    continue

            if uid not in issue_threads:
                issue_threads[uid] = {
                    "status": "open",
                    "file": update.get("file", "unknown"),
                    "approx_line": update.get("approx_line", 0),
                    "snippet": update.get("snippet", ""),
                    "severity": update.get("severity", "warning"),
                    "history": [],
                }
            issue_threads[uid]["status"] = update.get("status", "open")
            for key in ("file", "approx_line", "snippet", "severity"):
                if update.get(key):
                    issue_threads[uid][key] = update[key]
            reply = update.get("reply", "")
            if reply:
                # Inject status tag unless LLM already included one
                TAGS = ("[NEW]", "[REOPEN]", "[VERIFIED]", "[ACKED]")
                if not reply.strip().startswith(TAGS):
                    status = update.get("status", "open")
                    history_len = len(issue_threads[uid]["history"])
                    if history_len == 0:
                        tag = "[NEW]"
                    elif status == "resolved":
                        tag = "[VERIFIED]"
                    elif status == "acknowledged":
                        tag = "[ACKED]"
                    else:
                        tag = "[REOPEN]"
                    reply = f"{tag} {reply}"

                issue_threads[uid]["history"].append({
                    "role": "critic",
                    "content": reply,
                })

        # Scoreboard
        open_issues = {k: v for k, v in issue_threads.items() if v["status"] == "open"}
        resolved = {k: v for k, v in issue_threads.items() if v["status"] == "resolved"}
        acked = {k: v for k, v in issue_threads.items() if v["status"] == "acknowledged"}

        print(f"\n  Scoreboard: {len(open_issues)} open | {len(resolved)} resolved | {len(acked)} acknowledged")

        # Show open issues + just-closed issues (curtain call before they disappear)
        just_closed = [
            uid for uid in updates
            if uid in issue_threads and issue_threads[uid]["status"] in ("resolved", "acknowledged")
        ]
        display_uids = list(open_issues.keys()) + just_closed
        display_uids.sort(key=lambda x: int(x.split("-")[1]) if "-" in x and x.split("-")[1].isdigit() else 0)

        for uid in display_uids:
            issue = issue_threads[uid]
            status = issue["status"]

            if status == "resolved":
                label = "RESOLVED"
            elif status == "acknowledged":
                label = "ACKNOWLEDGED"
            else:
                label = issue.get("severity", "warning").upper()

            print(f"\n  [{uid}] {label} {issue.get('file', '?')}:~{issue.get('approx_line', '?')}")
            if issue.get("snippet") and status == "open":
                print(f"  Snippet: `{issue.get('snippet')}`")

            # Thread dialogue tree (tags already in content)
            print("  Thread:")
            history = issue.get("history", [])
            for idx, msg in enumerate(history):
                prefix = "  └─" if idx == len(history) - 1 else "  ├─"
                content = msg["content"].strip().replace("\n", " ")
                role = "Critic" if msg["role"] == "critic" else "Agent "
                print(f"  {prefix} {role}: {content}")

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
            def _feed_stdin(p, data):
                p.stdin.write(data)
                p.stdin.close()

            writer = threading.Thread(target=_feed_stdin, args=(proc, claude_prompt))
            writer.start()

            print("-" * 60)
            agent_lines = []
            for line in proc.stdout:
                print(line, end="", flush=True)
                agent_lines.append(line)
            print("-" * 60)

            writer.join()
            proc.wait()
            agent_output = "".join(agent_lines)

            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, "claude")

            # Parse structured reply (JSON primary + regex fallback)
            parsed_uids = set()

            # Try 1: strict JSON from <agent_reply> tags
            match = re.search(
                r"<agent_reply>\s*(\{.*?\})\s*</agent_reply>",
                agent_output,
                re.DOTALL,
            )
            if match:
                try:
                    replies = json.loads(match.group(1))
                    for uid, payload in replies.items():
                        if uid not in issue_threads:
                            continue
                        # Support both {"quote": "...", "reply": "..."} and plain string
                        if isinstance(payload, dict):
                            content = payload.get("reply", "")
                        else:
                            content = str(payload)
                        if content:
                            issue_threads[uid]["history"].append({
                                "role": "agent",
                                "content": content,
                            })
                            parsed_uids.add(uid)
                except json.JSONDecodeError:
                    pass

            # Try 2: regex fallback for unstructured Markdown output
            missing_uids = set(open_issues.keys()) - parsed_uids
            if missing_uids:
                for uid in missing_uids:
                    pattern = re.compile(
                        rf"{uid}.*?((?:Critic.*?)??\[(?:FIXED|NOT FIXED|DISAGREE)\].*?)(?=\bISSUE-\d+\b|\Z)",
                        re.IGNORECASE | re.DOTALL,
                    )
                    fallback_match = pattern.search(agent_output)
                    if fallback_match:
                        content = fallback_match.group(1).strip()
                        content = re.sub(r"^[-—\s*]*", "", content)
                        issue_threads[uid]["history"].append({
                            "role": "agent",
                            "content": content,
                        })
                        parsed_uids.add(uid)
                    else:
                        issue_threads[uid]["history"].append({
                            "role": "agent",
                            "content": "[parse failed] No structured reply or recognizable tag found.",
                        })

            print(f"[Agent] {len(parsed_uids)}/{len(open_issues)} responses parsed.\n")

        except FileNotFoundError:
            print("[A.R.C.] `claude` not found. Install: npm install -g @anthropic-ai/claude-code")
            break
        except subprocess.CalledProcessError as e:
            print(f"[A.R.C.] Agent crashed with code {e.returncode}")
            break
        except KeyboardInterrupt:
            print("\n[A.R.C.] Interrupted. Dumping partial report...")
            break

    # ── Battle Report (always runs, even on interrupt) ─────────

    print(f"\n{'=' * 60}")
    print("         A.R.C. Battle Report")
    print(f"{'=' * 60}")

    t_in, t_out, t_cached = _print_finops(critic)

    # Compute objective stats
    total = len(issue_threads)
    fixed = len([i for i in issue_threads.values() if i["status"] == "resolved"])
    acked = len([i for i in issue_threads.values() if i["status"] == "acknowledged"])
    open_count = len([i for i in issue_threads.values() if i["status"] == "open"])
    disagrees = sum(
        1 for i in issue_threads.values()
        for h in i["history"]
        if h["role"] == "agent" and "[DISAGREE]" in h["content"]
    )

    objective_stats = (
        f"- Total issues: {total}\n"
        f"- Resolved: {fixed}, Acknowledged: {acked}, Open: {open_count}\n"
        f"- Agent [DISAGREE] pushbacks: {disagrees}\n"
        f"- Input tokens: {t_in:,}, Output tokens: {t_out:,}, Cached: {t_cached:,}\n"
    )
    if acked > 0:
        objective_stats += f"- Critic was wrong on {acked} issue(s) (acknowledged = Critic error).\n"
    if disagrees >= 5:
        objective_stats += "- The Agent overwhelmingly dominated the debates. The Critic was frequently incorrect.\n"

    # Objective scoreboard
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

    # Critic's subjective audit
    try:
        print("\n  [Critic's Audit]")
        audit = critic.audit(issue_threads, objective_stats=objective_stats)
        print(audit)
    except (KeyboardInterrupt, Exception) as e:
        print(f"\n  [Critic's Audit] Skipped ({type(e).__name__})")

    print(f"{'=' * 60}")

    # Dump threads (always, even on partial run)
    print("\n--- Final Issue State (JSON) ---")
    print(json.dumps(issue_threads, indent=2, ensure_ascii=False))



def _print_finops(critic: CriticAgent) -> tuple[int, int, int]:
    """Print token usage stats and return (tokens_in, tokens_out, tokens_cached)."""
    t_in = getattr(critic.client, "tokens_in", 0)
    t_out = getattr(critic.client, "tokens_out", 0)
    t_cached = getattr(critic.client, "tokens_cached", 0)

    if t_in > 0 or t_out > 0:
        hit_ratio = (t_cached / t_in * 100) if t_in > 0 else 0.0
        print(f"\n  [FinOps]")
        print(f"  Input Tokens  : {t_in:,}")
        print(f"  Output Tokens : {t_out:,}")
        if t_cached > 0:
            print(f"  Cache Hits    : {t_cached:,} ({hit_ratio:.1f}%)")
        print(f"{'-' * 60}")

    return t_in, t_out, t_cached


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
