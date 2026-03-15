# A.R.C. — TODO

## v0.1.0 (done)

- [x] Multi-provider LLM abstraction (Anthropic, OpenAI, Gemini)
- [x] Brute-force repo context via `git ls-files` with noise filtering
- [x] Single-shot free-form review
- [x] CLI flags: `--scope`, `--rubric`, `--fix`, `--max-turns`, `--strict`
- [x] Blackboard Pattern: structured JSON issue threads
- [x] Democratic debate with `[FIXED]`/`[DISAGREE]`/`[NOT FIXED]` tags
- [x] Status tags injected into history (`[NEW]`/`[REOPEN]`/`[VERIFIED]`/`[ACKED]`)
- [x] Quote-the-thread: Agent must cite Critic's point
- [x] Smart reply parser: JSON primary + regex fallback
- [x] Double Jeopardy: fuzzy 3D matching (file + snippet + ±5 line radius)
- [x] Absolute lock: no zombie re-opening of closed issues
- [x] Res Judicata: no re-arguing settled topics under new IDs
- [x] Verify the Diff: Critic checks git diff before accepting `[FIXED]`
- [x] FinOps token panel (Gemini usage_metadata tracking)
- [x] Objective scoring: Python stats force honest Critic self-assessment
- [x] Battle Report with MVP calculation
- [x] Thread dialogue tree in scoreboard
- [x] Curtain call for just-closed issues
- [x] Graceful interrupt: partial report on timeout/ctrl-c
- [x] `pyproject.toml` for pip distribution
- [x] 50+ tests

## v0.2.0 (next)

- [ ] Streaming Critic output (show review as it arrives)
- [ ] Token usage tracking for Anthropic and OpenAI clients
- [ ] Configurable thinking budget for Gemini
- [ ] Save battle report to file (`--output report.json`)
- [ ] GitHub Action: publish to PyPI on tag
- [ ] Homebrew formula

## Future

- [ ] Custom rubric authoring guide
- [ ] Multi-repo batch review
