---
name: job-copilot
description: 针对一个具体职位(JD)做求职准备:预检 JD 硬性门槛,调用求职 Copilot 后端完成简历-JD 匹配分析、简历定制和面试压力测试。用户给出 JD 并想知道"能不能投""匹配度如何""帮我改简历""面试会被问什么"时使用。
---

# 求职 Copilot

把一份简历对准一个 JD,按顺序做四件事:门槛预检 → 匹配分析 → 简历定制 → 面试压力测试。
每一步做完先给用户看结果、等确认,不要一口气跑完再汇报。

## 前置条件

- 后端已启动:本地 `cd backend && venv/bin/uvicorn app.main:app`(默认 `http://localhost:8000`),
  或 `docker compose up -d`(此时设置 `JOB_COPILOT_URL=http://localhost:8080`)。
- 需要用户的简历文件(PDF / DOCX)和 JD 文本。JD 是截图时,先转写成文字存为 txt。

## 第 1 步:门槛预检(规则,不调模型)

```bash
python .claude/skills/job-copilot/scripts/precheck.py jd.txt
```

输出每个命中项的类别、关键词、`level`(hard / soft)和原句。
- **hard** 项逐条拿去问用户是否满足(学校层次、毕业时间、留服认证、证书、户口等)。
  用户不满足时**先停下**,说明原因并询问是否仍要投,不要直接生成简历。
- **soft** 项("优先""加分")只需在最后提一句。
- 没有命中不代表没有门槛,规则只覆盖常见写法,快速通读一遍 JD 原文。

## 第 2–4 步:匹配、定制、压力测试

```bash
python .claude/skills/job-copilot/scripts/copilot.py run --resume 简历.pdf --jd jd.txt --steps match
```

- `--steps` 可选 `match`、`tailor`、`stress` 的任意组合,逗号分隔;默认三步全跑。
- `--market china|us` 指定简历规范;不传时采用后端识别结果(关键词规则优先,模糊时 LLM 兜底),
  输出里的 `market_style_source` 会说明来源,来自 LLM 时向用户确认一次。
- 建议先只跑 `match`,把结果给用户看过,再跑 `tailor,stress`。

### 如何呈现结果

- **匹配**:给出分数、已匹配技能、缺失技能。缺失技能要**变成问题问用户**("JD 要求 X,你做过吗?"),
  不能自己补进简历。
- **定制**:直接展示定制简历。方括号占位符(如 `[起止时间]`)逐个列出,请用户补全。
- **压力测试**:按经历分组列出追问。只给回忆思路,**不要替用户写答案**,也不要编造数字来源。

## 真实性约束(优先级最高)

- 只能重组、改写简历里已有的事实。用户口头补充的新经历,先问清角色、规模、时间和可验证的结果再写。
- 不升级角色("参与"不能变成"主导"),团队成果要写明是团队。
- 不写简历中没有的签证、户口、证书信息。

## 其他

- 查看本次会话花了多少钱:`python .claude/skills/job-copilot/scripts/copilot.py usage`
- 脚本出错时会在 stderr 打印 `{"error": ...}` 并以退出码 1 结束;连不上后端时提示用户启动服务,不要绕过后端自己生成。
