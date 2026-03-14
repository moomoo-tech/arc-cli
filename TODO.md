# A.R.C. — TODO

## Phase 1: First PR Comment Locally (MVP)

- [x] Webhook signature verification (`webhook_receiver.py`)
- [x] PyGithub fetch diff + post comments (`githandler/client.py`)
- [x] Rubric YAML loading + formatting (`rubric_parser.py`)
- [x] **Wire up LLM call** — `critic_agent.py` calls Claude API, parses structured comments
- [x] **Wire up webhook dispatch** — `webhook_receiver.py` calls CriticAgent + GitHubClient, posts PR comments
- [x] **Critic auto-generates `<architectural_directive>` XML comments**
- [ ] Configure `.env` (PAT + Anthropic key)
- [ ] Local e2e test with smee.io + FastAPI

## Phase 2: Local Actor (Aider Auto-Execution)

- [x] **Webhook routing** — `issue_comment` event triggers Actor flow
- [x] **XML extraction** — `extract_directives()` parses `<architectural_directive>` tags
- [x] **Aider invocation** — `run_actor()` checkout branch → aider --auto-commits → git push
- [x] **Infinite loop prevention** — `bot_username` filter, only process own comments
- [ ] Install Aider (`pip install aider-chat`)
- [ ] Configure `ARC_LOCAL_REPO_PATH` and `ARC_BOT_USERNAME`
- [ ] E2e validation: PR → Critic comments → Actor fixes code → push

## Phase 3: Migrate to GCP Cloud Functions (Critic in the Cloud)

- [ ] Create `main.py` (`functions_framework.http` entry point)
- [ ] Migrate secrets to GCP Secret Manager, inject via env vars
- [ ] `gcloud functions deploy`
- [ ] Point GitHub App Webhook URL to GCP Function URL
- [ ] `.gcloudignore` to exclude local_runner/
- [ ] Keep only Actor locally (webhook listener or polling)

## Phase 4: Show Time

- [ ] Submit PR in target repo → Critic auto-comments
- [ ] Local Actor activates → Aider auto-fixes → push
- [ ] Push triggers synchronize → Critic re-reviews
- [ ] End-to-end AI dev loop validation
