# 简历定制幻觉率测试

衡量「简历定制」功能会不会编造用户没有的内容，并对比加约束前后的效果。

## 原理

1. 每个用例（原始简历 + JD）分别用三种 prompt 生成定制简历：
   - `current`：线上实际使用的 `build_tailor_prompt`
   - `v1`：加入第 6–8 条规则（角色界定、不添加效果、总结须有依据）之前的线上 prompt
   - `baseline`：去掉所有防编造约束的朴素 prompt，作为对照组
2. 由独立的评审模型（`claude-opus-5-5`）把定制简历拆成一条条事实陈述，逐条对照原始简历，标为 `supported`（有依据）/ `placeholder`（占位符）/ `fabricated`（编造或夸大），编造的再细分为数字、经历、技能、夸大角色、身份信息等类型。
3. 另外用规则统计「定制简历中新出现、原简历里没有的数字」，作为对评审结果的交叉核对。

## 指标

- **陈述级编造率** = 编造条数 / 总陈述数
- **输出级编造率** = 含至少 1 处编造的简历占比（更贴近用户感受：拿到的简历能不能直接用）

## 运行

在 `backend/` 目录下：

```bash
venv/bin/python -m evals.hallucination_eval --dry-run
```

```bash
venv/bin/python -m evals.hallucination_eval --runs 3
```

- `--dry-run`：只打印计划和预估费用，不调用 API
- `--runs N`：每个用例每组重复 N 次（生成有随机性，建议 3）
- `--cases a b`：只跑指定用例
- `--variants current baseline`：只跑指定的组

结果写在 `evals/results/<时间>/`：`report.md`（总览 + 逐条编造明细）、`summary.json`、`raw.jsonl`（完整生成内容和评审结果）。

## 添加用例

在 `cases/` 下新建一个目录：

- `resume.txt` / `resume.pdf` / `resume.docx`：原始简历
- `jd.txt`：目标 JD
- `meta.json`（可选）：`{"market_style": "china"}` 或 `"us"`，默认 `china`

现有 20 个用例（4 个手写 + 16 个虚构），覆盖：简历内容很少、跨岗位转行、JD 要求简历里没有的技能/年限/身份信息（签证、户口）、团队项目、中英文等情况。部分用例：

| 用例 | 测试点 |
|---|---|
| `ai_pm_real` | 真实简历 + AI 产品经理 JD |
| `ops_to_pm` | 运营转产品，原简历无任何数字，JD 要求 SQL / A/B 测试 |
| `us_swe_visa` | 北美 JD 要求美国工作授权、Kubernetes、量化成果，原简历都没有 |
| `thin_algo` | 简历极薄，JD 要求 PyTorch、顶会论文、户口 |
| `pm_seniority` | 实习生投高级产品经理，JD 要求 5 年经验、带团队 |
| `ml_team_us` | 全是团队项目，JD 偏好 "led" 项目经验 |
| `sales_us` | JD 要求写出销售配额完成率，原简历只有实习 |

## 注意

评审本身也是 LLM，可能误判。写进简历或面试前，请抽查 `report.md` 里的编造明细，把误判条目剔除后再算最终数字。
