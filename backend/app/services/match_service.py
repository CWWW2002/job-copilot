import json
import re

from app.services.llm_client import complete

MAX_RESUME_CHARS = 6000
MAX_JD_CHARS = 4000

MARKET_STYLE_LABELS = {"us": "北美", "china": "中国大陆"}

MARKET_STYLE_HINTS = {
    "us": "北美市场通常注重简历与JD关键词的精确匹配(考虑ATS筛选)、量化的项目成果,以及是否需要visa sponsorship。",
    "china": "中国大陆市场通常注重学历背景、实习/项目经历与岗位职责的对应关系,以及户口、base城市等要求。",
}


class MatchReportParseError(Exception):
    pass


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    return json.loads(text)


def build_prompt(resume_text: str, jd_text: str, market_style: str) -> str:
    market_label = MARKET_STYLE_LABELS.get(market_style, market_style)
    market_hint = MARKET_STYLE_HINTS.get(market_style, "")

    return f"""你是一位专业的求职简历顾问,请基于下面的简历和职位描述(JD),给出结构化的匹配分析。
这份JD按{market_label}招聘市场的标准来评估。{market_hint}

请只输出一个JSON对象,不要有任何其他文字、解释或markdown代码块标记,格式如下:
{{
  "score": <0到100的整数,表示简历与JD的总体匹配度>,
  "matched_skills": [
    {{
      "skill": "<技能或经验点,中英文都给出,格式为'中文名称 / English Name'>",
      "evidence": "<引用简历中的具体原文片段作为依据,保持简历原文的语言,不要翻译>"
    }}
  ],
  "missing_skills": [
    "<JD要求但简历中未体现或不匹配的技能/经验点,格式为'中文名称 / English Name'>"
  ],
  "summary": {{
    "zh": "<一句话总结建议(中文),给出下一步该怎么改进简历或是否值得投递>",
    "en": "<the same one-sentence summary and advice, in English>"
  }}
}}

简历内容:
---
{resume_text[:MAX_RESUME_CHARS]}
---

职位描述:
---
{jd_text[:MAX_JD_CHARS]}
---
"""


def generate_match_report(resume_text: str, jd_text: str, market_style: str) -> dict:
    prompt = build_prompt(resume_text, jd_text, market_style)
    raw_text = complete("match", prompt, max_tokens=2000)

    try:
        data = _extract_json(raw_text)
    except json.JSONDecodeError as e:
        raise MatchReportParseError(f"无法解析LLM返回的JSON: {raw_text[:200]}") from e

    score = data.get("score")
    if not isinstance(score, int):
        try:
            score = int(score)
        except (TypeError, ValueError):
            raise MatchReportParseError("LLM返回的score字段不是有效数字")
    score = max(0, min(100, score))

    summary = data.get("summary") or {}
    if not isinstance(summary, dict):
        raise MatchReportParseError("LLM返回的summary字段格式不正确")

    return {
        "score": score,
        "matched_skills": data.get("matched_skills", []),
        "missing_skills": data.get("missing_skills", []),
        "summary_zh": summary.get("zh", ""),
        "summary_en": summary.get("en", ""),
    }
