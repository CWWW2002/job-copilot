# 求职 Copilot

基于大模型的求职辅助工具：简历与 JD 匹配分析、针对 JD 的简历定制、面试压力测试（模拟面试官针对简历逐条追问）。

![CI](https://github.com/CWWW2002/job-copilot/actions/workflows/ci.yml/badge.svg)

## 功能

- **简历-JD 匹配**：给出匹配度评分、已匹配 / 缺失技能，并逐条引用简历原文作为依据
- **简历定制**：按国内 / 北美简历规范改写，禁止编造经历、数字和身份信息，缺失处以占位符提示
- **面试压力测试**：按经历分组生成追问（数字来源、个人 vs 团队贡献、技术选型、时间线），只给回忆思路，不替用户写答案
- **JD 市场风格识别**：关键词规则优先，规则判断不了才交给 LLM

## 架构

```
React (Vite) ──▶ Nginx ──/api──▶ FastAPI ──▶ LLM 调用层(LiteLLM Router) ──▶ Claude
                                   │              ├─ light:  claude-haiku-5-5   (分类任务)
                                   │              ├─ main:   claude-sonnet-4-6  (生成任务)
                                   │              └─ fallback: claude-sonnet-5-5 (主力失败时兜底)
                                   └──▶ SQLite（业务数据 + 每次 LLM 调用的 token / 成本记录）
```

- **多模型路由与成本追踪**：所有 LLM 调用统一经过 [`llm_client.py`](backend/app/services/llm_client.py)，按任务路由到不同模型，失败自动重试和兜底，并记录每次调用的模型、token、成本与耗时；`GET /api/usage` 返回按任务、按模型的成本统计。
- **幻觉率评测**：[`backend/evals`](backend/evals) 用「LLM 评审 + 规则核对」把定制简历拆成事实陈述逐条核验，对比线上 prompt、旧版 prompt 与无约束对照组的编造率。

## 运行

```bash
cp backend/.env.example backend/.env   # 填入 ANTHROPIC_API_KEY
docker compose up -d --build           # 访问 http://localhost:8080
```

本地开发：

```bash
cd backend && python -m venv venv && venv/bin/pip install -r requirements-dev.txt
venv/bin/uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

## 测试与 CI

```bash
cd backend && venv/bin/pytest -q
```

单元测试覆盖模型路由、兜底、失败记录、成本统计接口与评测 prompt，LLM 调用全部 mock，无需 API key。GitHub Actions 在每次提交时运行后端测试、评测脚本 dry-run、前端 lint 与构建，以及前后端镜像构建。
