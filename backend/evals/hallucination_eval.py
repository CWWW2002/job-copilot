"""简历定制功能的幻觉率测试。

对每个测试用例(原始简历 + JD),分别用两种 prompt 生成定制简历:
- current:  线上实际使用的 build_tailor_prompt(带"禁止编造"等硬性约束)
- baseline: 去掉防编造约束的朴素 prompt,作为对照组

再用一个独立的 LLM 评审,把定制简历拆成一条条事实陈述,逐条对照原始简历判断是否编造,
最终统计编造率,并输出逐条明细供人工复核。

用法(在 backend/ 目录下):
    venv/bin/python -m evals.hallucination_eval --dry-run        # 只打印计划和预估费用,不调用 API
    venv/bin/python -m evals.hallucination_eval --runs 3         # 正式运行
"""

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

from app.services.llm_client import MODEL_NAME, complete, get_client  # noqa: E402
from app.services.parser import parse_resume  # noqa: E402
from app.services.tailor_service import (  # noqa: E402
    CHINA_STYLE_RULES,
    MAX_JD_CHARS,
    MAX_RESUME_CHARS,
    US_STYLE_RULES,
    build_tailor_prompt,
)

EVALS_DIR = Path(__file__).resolve().parent
CASES_DIR = EVALS_DIR / "cases"
RESULTS_DIR = EVALS_DIR / "results"

JUDGE_MODEL = "claude-opus-5-5"
GEN_MAX_TOKENS = 3000  # 与 tailor_service.generate_tailored_resume 保持一致

# 粗略单价(美元 / 百万 token),仅用于 --dry-run 估算
PRICES = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}

VARIANTS = ("current", "v1", "baseline")
VARIANT_LABELS = {
    "current": "current(现行 prompt)",
    "v1": "v1(加强前的 prompt)",
    "baseline": "baseline(无防编造约束)",
}

# ---------- 对照组 prompt:去掉防编造约束 ----------

US_STYLE_RULES_NO_GUARD = US_STYLE_RULES.replace(
    "- 如果原简历中已有具体数字(百分比、指标等),保留并突出;如果原简历没有具体数字,绝对不能编造数字,只能把原有描述改写成更符合动词开头、STAR结构的句式",
    "- 尽量用具体数字和量化成果体现影响力",
)
assert US_STYLE_RULES_NO_GUARD != US_STYLE_RULES, "tailor_service 的 US_STYLE_RULES 已改动,请同步更新对照组"

BASELINE_STYLE_RULES = {"us": US_STYLE_RULES_NO_GUARD, "china": CHINA_STYLE_RULES}


def build_baseline_prompt(resume_text: str, jd_text: str, market_style: str) -> str:
    style_rules = BASELINE_STYLE_RULES.get(market_style, US_STYLE_RULES_NO_GUARD)
    return f"""你是一位专业的求职简历顾问。请基于用户的原始简历和目标职位描述(JD),生成一份针对这个JD定制过的简历,尽可能突出与岗位的匹配度。

{style_rules}

请直接输出定制后的简历全文(Markdown格式纯文本),不要输出任何解释、前言或后记,不要用代码块包裹。

原始简历:
---
{resume_text[:MAX_RESUME_CHARS]}
---

目标职位描述(JD):
---
{jd_text[:MAX_JD_CHARS]}
---
"""


# v1:加入第 6-8 条规则(角色界定、不添加效果、总结须有依据)之前的线上 prompt,用于对比这次优化的效果
V1_REMOVED_RULES = re.compile(r"\n6\. 保留原文对个人角色的界定.*?\n8\. [^\n]*", re.DOTALL)


def build_v1_prompt(resume_text: str, jd_text: str, market_style: str) -> str:
    prompt = build_tailor_prompt(resume_text, jd_text, market_style)
    v1_prompt = V1_REMOVED_RULES.sub("", prompt)
    assert v1_prompt != prompt, "tailor_service 的核心原则已改动,请同步更新 v1 对照组"
    return v1_prompt


PROMPT_BUILDERS = {"current": build_tailor_prompt, "v1": build_v1_prompt, "baseline": build_baseline_prompt}

# ---------- 评审 ----------

FABRICATION_TYPES = ["number", "experience", "skill", "scope_inflation", "identity", "other"]

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "label": {"type": "string", "enum": ["supported", "placeholder", "fabricated"]},
                    "fabrication_type": {"type": "string", "enum": FABRICATION_TYPES + ["none"]},
                    "evidence": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["claim", "label", "fabrication_type", "evidence", "explanation"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

JUDGE_PROMPT = """你是一位严格的简历事实核查员。下面有一份【原始简历】和一份根据它改写的【定制简历】。
你的任务是找出定制简历中所有原始简历无法支持的内容。

步骤:
1. 把【定制简历】拆成一条条独立的事实陈述(claim):每段经历的职责、成果、数字、使用的工具/技能、公司/职位/时间、协作对象、个人身份信息(签证、户口、国籍等)等。纯格式、标题、联系方式中与原文一致的部分可以合并成一条或省略;不要遗漏任何具体事实。
2. 对每条陈述,对照【原始简历】打标签:
   - supported:原始简历明确写了,或是忠实的换种说法(措辞更专业、合并精简都算 supported)
   - placeholder:用方括号等方式明确标注为待补充的占位内容,如 [起止时间]
   - fabricated:原始简历没有、与原文矛盾,或夸大了原文(例如"参与"变成"主导"、"协助"变成"负责"、凭空加上数字或效果)
3. fabricated 的必须填写 fabrication_type:
   - number:编造或改动了数字、百分比、规模
   - experience:编造了原文没有的经历、项目、职责、协作对象、成果
   - skill:编造了原文没有的技能、工具、证书
   - scope_inflation:夸大了个人角色或影响范围
   - identity:编造了签证/工作授权/户口/国籍/年龄等身份信息
   - other:其他
   非 fabricated 的 fabrication_type 填 "none"。
4. evidence 填原始简历中最相关的原文片段(找不到就填空字符串);explanation 用一句话说明判断理由。

判断要严格:宁可把可疑的夸大标为 fabricated,也不要放过。但合理的同义改写、翻译、删减不算编造。

【原始简历】
---
{resume}
---

【定制简历】
---
{tailored}
---
"""

# ---------- 用例加载 ----------


def load_cases(only: list[str] | None) -> list[dict]:
    cases = []
    for case_dir in sorted(p for p in CASES_DIR.iterdir() if p.is_dir()):
        if only and case_dir.name not in only:
            continue
        resume_files = sorted(case_dir.glob("resume.*"))
        jd_file = case_dir / "jd.txt"
        if not resume_files or not jd_file.exists():
            print(f"跳过 {case_dir.name}:缺少 resume.* 或 jd.txt")
            continue
        resume_file = resume_files[0]
        if resume_file.suffix.lower() in (".pdf", ".docx"):
            _, resume_text = parse_resume(resume_file.name, resume_file.read_bytes())
        else:
            resume_text = resume_file.read_text(encoding="utf-8")
        meta_file = case_dir / "meta.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
        cases.append(
            {
                "name": case_dir.name,
                "resume": resume_text.strip(),
                "jd": jd_file.read_text(encoding="utf-8").strip(),
                "market_style": meta.get("market_style", "china"),
            }
        )
    return cases


# ---------- 调用 ----------


def generate(prompt: str) -> str:
    # 与线上简历定制走同一条 LiteLLM 路由
    return complete("eval_generate", prompt, max_tokens=GEN_MAX_TOKENS).strip()


def judge(client: anthropic.Anthropic, resume: str, tailored: str) -> list[dict]:
    response = client.beta.messages.create(
        model=JUDGE_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(resume=resume, tailored=tailored)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("评审模型拒绝了该请求")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("评审输出被截断(max_tokens)")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["claims"]


NUMBER_RE = re.compile(r"\d{2,}")


def new_numbers(original: str, tailored: str) -> list[str]:
    """定制简历中出现、但原始简历里没有的数字。作为评审结果的交叉核对,不进入主指标。
    按连续数字比较,这样 2024-09 改写成 2024.09 不算新数字;个位数(多为列表序号)忽略。"""
    original_numbers = set(NUMBER_RE.findall(original))
    return sorted({n for n in NUMBER_RE.findall(tailored) if n not in original_numbers})


def run_one(client: anthropic.Anthropic, case: dict, variant: str, run: int) -> dict:
    prompt = PROMPT_BUILDERS[variant](case["resume"], case["jd"], case["market_style"])
    record = {"case": case["name"], "variant": variant, "run": run}
    try:
        tailored = generate(prompt)
        claims = judge(client, case["resume"], tailored)
        record.update(tailored=tailored, claims=claims, new_numbers=new_numbers(case["resume"], tailored))
    except (anthropic.APIError, RuntimeError, json.JSONDecodeError) as e:
        record["error"] = f"{type(e).__name__}: {e}"
    return record


# ---------- 统计与报告 ----------


def summarize(records: list[dict]) -> dict:
    summary = {}
    for variant in [v for v in VARIANTS if any(r["variant"] == v for r in records)]:
        rows = [r for r in records if r["variant"] == variant and "claims" in r]
        claims = [c for r in rows for c in r["claims"]]
        fabricated = [c for c in claims if c["label"] == "fabricated"]
        by_type = {t: sum(1 for c in fabricated if c["fabrication_type"] == t) for t in FABRICATION_TYPES}
        summary[variant] = {
            "outputs": len(rows),
            "errors": sum(1 for r in records if r["variant"] == variant and "error" in r),
            "claims": len(claims),
            "fabricated": len(fabricated),
            "claim_fabrication_rate": len(fabricated) / len(claims) if claims else None,
            "outputs_with_fabrication": sum(1 for r in rows if any(c["label"] == "fabricated" for c in r["claims"])),
            "output_fabrication_rate": (
                sum(1 for r in rows if any(c["label"] == "fabricated" for c in r["claims"])) / len(rows)
                if rows
                else None
            ),
            "placeholders": sum(1 for c in claims if c["label"] == "placeholder"),
            "fabricated_by_type": by_type,
            "new_numbers": sum(len(r["new_numbers"]) for r in rows),
        }
    return summary


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def write_report(out_dir: Path, records: list[dict], summary: dict, args: argparse.Namespace) -> None:
    lines = [
        "# 简历定制幻觉率测试报告",
        "",
        f"- 时间:{datetime.now():%Y-%m-%d %H:%M}",
        f"- 生成模型:`{MODEL_NAME}`;评审模型:`{JUDGE_MODEL}`",
        f"- 用例数:{len({r['case'] for r in records})};每个用例每组运行 {args.runs} 次",
        "",
        "## 总览",
        "",
    ]
    variants = list(summary)
    lines += [
        "| 指标 | " + " | ".join(VARIANT_LABELS[v] for v in variants) + " |",
        "|---|" + "---|" * len(variants),
    ]
    metrics = [
        ("陈述级编造率(编造条数 / 总陈述数)", lambda s: pct(s["claim_fabrication_rate"])),
        ("输出级编造率(含 ≥1 处编造的简历占比)", lambda s: pct(s["output_fabrication_rate"])),
        ("编造条数 / 总陈述数", lambda s: f"{s['fabricated']} / {s['claims']}"),
        ("占位符条数", lambda s: s["placeholders"]),
        ("新出现的数字个数(规则交叉核对)", lambda s: s["new_numbers"]),
        ("失败次数", lambda s: s["errors"]),
    ]
    metrics += [(f"编造类型:{t}", lambda s, t=t: s["fabricated_by_type"][t]) for t in FABRICATION_TYPES]
    lines += ["| " + name + " | " + " | ".join(str(fn(summary[v])) for v in variants) + " |" for name, fn in metrics]
    lines += [
        "",
        "> 评审由 LLM 完成,可能误判。写进简历或拿去面试前,请抽查下面的明细,",
        "> 把误判的条目记下来,用人工修正后的数字作为最终结果。",
        "",
        "## 编造明细(供人工复核)",
    ]
    for r in sorted(records, key=lambda r: (r["case"], r["variant"], r["run"])):
        header = f"### {r['case']} · {r['variant']} · 第 {r['run']} 次"
        if "error" in r:
            lines += ["", header, "", f"运行失败:{r['error']}"]
            continue
        fabricated = [c for c in r["claims"] if c["label"] == "fabricated"]
        lines += ["", header, "", f"共 {len(r['claims'])} 条陈述,编造 {len(fabricated)} 条"]
        if r["new_numbers"]:
            lines.append(f"新出现的数字:{', '.join(r['new_numbers'])}")
        for c in fabricated:
            lines.append(f"- **[{c['fabrication_type']}]** {c['claim']}  \n  理由:{c['explanation']}")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def estimate_cost(cases: list[dict], runs: int, variants: list[str]) -> float:
    gen_in, gen_out = PRICES.get(MODEL_NAME, PRICES["claude-sonnet-4-6"])
    judge_in, judge_out = PRICES[JUDGE_MODEL]
    total = 0.0
    for case in cases:
        prompt_tokens = (len(case["resume"]) + len(case["jd"]) + 1500) * 0.8  # 中文约 0.8 token/字,粗估
        per_run = (
            prompt_tokens * gen_in + 2000 * gen_out  # 生成
            + (len(case["resume"]) * 0.8 + 2000 + 1500) * judge_in + 6000 * judge_out  # 评审(含思考)
        ) / 1_000_000
        total += per_run * len(variants) * runs
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="简历定制功能幻觉率测试")
    parser.add_argument("--runs", type=int, default=1, help="每个用例每组重复次数(生成有随机性,建议 3)")
    parser.add_argument("--cases", nargs="*", help="只跑指定用例(目录名)")
    parser.add_argument("--variants", nargs="*", choices=VARIANTS, default=list(VARIANTS), help="要跑的组")
    parser.add_argument("--workers", type=int, default=4, help="并发数")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划与预估费用,不调用 API")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    if not cases:
        raise SystemExit(f"在 {CASES_DIR} 下没有找到可用的测试用例")

    jobs = [(case, variant, run) for case in cases for variant in args.variants for run in range(1, args.runs + 1)]
    print(f"用例 {len(cases)} 个 × {len(args.variants)} 组 × {args.runs} 次 = {len(jobs)} 次生成 + {len(jobs)} 次评审")
    print(f"生成模型 {MODEL_NAME},评审模型 {JUDGE_MODEL}")
    print(f"预估费用约 ${estimate_cost(cases, args.runs, args.variants):.2f}(粗估,以账单为准)")
    if args.dry_run:
        for case in cases:
            print(f"  - {case['name']}({case['market_style']}):简历 {len(case['resume'])} 字,JD {len(case['jd'])} 字")
        return

    client = get_client()
    out_dir = RESULTS_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True)

    records = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool, open(out_dir / "raw.jsonl", "w", encoding="utf-8") as raw:
        futures = [pool.submit(run_one, client, *job) for job in jobs]
        for i, future in enumerate(as_completed(futures), 1):
            record = future.result()
            records.append(record)
            raw.write(json.dumps(record, ensure_ascii=False) + "\n")
            raw.flush()
            status = record.get("error") or f"编造 {sum(c['label'] == 'fabricated' for c in record['claims'])} 条"
            print(f"[{i}/{len(jobs)}] {record['case']} · {record['variant']} · 第 {record['run']} 次:{status}")

    summary = summarize(records)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(out_dir, records, summary, args)

    print(f"\n完成,用时 {time.time() - started:.0f} 秒。结果在 {out_dir}")
    for variant in summary:
        s = summary[variant]
        print(
            f"  {variant:8s} 陈述级编造率 {pct(s['claim_fabrication_rate'])}"
            f"({s['fabricated']}/{s['claims']}),输出级编造率 {pct(s['output_fabrication_rate'])}"
        )


if __name__ == "__main__":
    main()
