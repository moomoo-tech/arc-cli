# A.R.C. — TODO

## Phase 1: 本地跑通第一条 PR 评论 (MVP)

- [x] Webhook 签名验证 (`webhook_receiver.py`)
- [x] PyGithub 拉 diff + 发评论 (`githandler/client.py`)
- [x] Rubric YAML 加载 + 格式化 (`rubric_parser.py`)
- [x] **接通 LLM 调用** — `critic_agent.py` 调 Claude API，解析结构化评论
- [x] **接通 webhook dispatch** — `webhook_receiver.py` 调 CriticAgent + GitHubClient，PR 里留评论
- [x] **Critic 自动生成 `<architectural_directive>` XML 评论**
- [ ] 配置 `.env`（PAT + Anthropic key）
- [ ] 本地用 smee.io + FastAPI 验证端到端

## Phase 2: 本地 Actor (Aider 自动执行)

- [x] **webhook 路由** — `issue_comment` 事件触发 Actor 流程
- [x] **XML 提取** — `extract_directives()` 解析 `<architectural_directive>` 标签
- [x] **Aider 调用** — `run_actor()` checkout branch → aider --auto-commits → git push
- [x] **防无限循环** — `bot_username` 过滤，只处理自己发的评论
- [ ] 安装 Aider（`pip install aider-chat`）
- [ ] 配置 `ARC_LOCAL_REPO_PATH` 和 `ARC_BOT_USERNAME`
- [ ] 端到端验证：PR → Critic 评论 → Actor 改代码 → push

## Phase 3: 迁移到 GCP Cloud Functions（Critic 上云）

- [ ] 新建 `main.py`（`functions_framework.http` 入口）
- [ ] 密钥迁移到 GCP Secret Manager，环境变量注入
- [ ] `gcloud functions deploy` 部署
- [ ] GitHub App Webhook URL 指向 GCP Function URL
- [ ] `.gcloudignore` 排除 local_runner/
- [ ] 本地只保留 Actor（webhook 监听 or 轮询）

## Phase 4: 肌肉展示 (Show Time)

- [ ] 在业务仓库提 PR → Critic 自动评论
- [ ] 本地 Actor 激活 → Aider 自动修复 → 推送
- [ ] push 触发 synchronize → Critic 二次审查
- [ ] 端到端 AI 研发闭环验证
