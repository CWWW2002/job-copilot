import json
import re

from app.services.llm_client import complete

MAX_RESUME_CHARS = 6000
MAX_JD_CHARS = 3000

BASE_RULES = """生成规则(必须严格遵守):
1. 如果某段经历里出现任何量化数据(百分比、金额、人数、时间周期、次数等),这一组里必须至少有一条"数字来源"类追问,追问这个数字具体是怎么算出来的、统计口径/数据来源是什么。
2. 如果某段经历的描述中出现"我们""团队"等字眼,或明显是多人协作/跨部门合作,必须生成至少一条"个人贡献 vs 团队贡献"类追问,要求区分本人具体负责的部分和团队其他人负责的部分。
3. 如果某段经历提到了具体的工具/框架/方法/策略,生成至少一条"技术选型"类追问,追问当时为什么选这个方案而不是其他备选方案。
4. 如果多段经历的时间有重叠,或某段经历持续时间很短但描述的成果/职责很多,生成至少一条"时间线合理性"类追问,要求解释时间线是否说得通。
5. 每段经历生成2到5条追问,不允许出现"说说你的这段经历"这种空泛、通用、换成任何简历都能套用的问题。每条追问都必须能明显看出是基于这份简历的具体文字生成的,而不是通用模板。
6. 追问语气要像真实面试官那样直接、略带质疑,不要用委婉客气的措辞包装。"""

JD_RULE = """5b. 已提供目标职位描述(JD)。针对JD中强调的能力要求,额外生成至少一条"JD关联"类追问——可以追问某段经历如何具体体现了JD要求的某项能力,或者对与JD关联度不高的经历追问它和目标岗位的关系。"""

ANSWER_GUIDANCE_RULES = """"answer_guidance" 字段的写法(必须严格遵守):
只提供"回忆 / 组织答案思路"的引导框架,绝对不能替用户编造具体的数字、具体原因或具体结论——这些只有用户自己知道。根据 type 按以下方向引导:
- 数字来源:提示用户回忆当时的统计口径(同比/环比/绝对值等)、基数、数据来源(后台报表/第三方工具/人工统计等);如果记不清具体数字,至少要能说清楚计算逻辑。
- 个人贡献 vs 团队贡献:提示用户按"我具体负责的模块/环节是什么、团队其他人负责什么、我们之间怎么协作"这个框架去梳理,不要替用户下结论说贡献具体是什么。
- 技术选型:提示用户回忆当时还考虑过哪些备选方案、最终选择的原因可能来自哪些维度(成本/时间/效果/团队熟悉度等),不要替用户编造选型理由。
- 时间线合理性:提示用户回忆这段时间是否并行处理了多件事、是否有交接或衔接安排,帮用户理清可以怎么解释,不要替用户编造具体安排。
- JD关联:提示用户注意这个岗位在意哪些能力(可参考JD原文),回答时可以着重强调这段经历里具体怎样体现了这些能力,但不要直接写出完整的回答句子。
- 其他:给出一个通用的"回忆细节、结构化表达"的提示,同样不能替用户下结论。"""


class StressTestParseError(Exception):
    pass


def _extract_json(text: str) -> list:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\[.*\])\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    return json.loads(text)


def build_prompt(resume_text: str, jd_text: str | None) -> str:
    has_jd = bool(jd_text and jd_text.strip())

    type_enum = '"数字来源" / "个人贡献 vs 团队贡献" / "技术选型" / "时间线合理性"'
    if has_jd:
        type_enum += ' / "JD关联"'
    type_enum += ' / "其他"'

    rules = BASE_RULES
    if has_jd:
        rules += "\n" + JD_RULE

    jd_block = ""
    if has_jd:
        jd_block = f"\n目标职位描述(JD):\n---\n{jd_text[:MAX_JD_CHARS]}\n---\n"

    return f"""你是一位经验丰富、以犀利追问著称的技术面试官。你的任务不是模拟"介绍一下这段经历"这类开放式问题,而是像面试官核实简历真实性和深度时那样,针对简历里的具体描述提出高度针对性的追问("压力测试")。

请仔细阅读下面这份简历,按其中出现的每一段工作经历 / 项目经历分组,为每一组生成追问清单。

{rules}

每条追问需要包含以下字段:
- "question": 追问原文
- "type": 从这些里选一个最贴切的:{type_enum}
- "why_asked": 一句话说明面试官为什么会这样追问,帮用户理解追问逻辑,而不只是死记硬背答案
- "answer_guidance": 见下方说明

{ANSWER_GUIDANCE_RULES}

只输出一个JSON数组,不要有任何其他文字、解释或markdown代码块标记,格式如下:
[
  {{
    "experience_title": "经历标题(如:XX公司产品经理实习)",
    "questions": [
      {{"question": "...", "type": "...", "why_asked": "...", "answer_guidance": "..."}}
    ]
  }}
]

简历内容:
---
{resume_text[:MAX_RESUME_CHARS]}
---
{jd_block}"""


def generate_stress_test(resume_text: str, jd_text: str | None = None) -> list:
    prompt = build_prompt(resume_text, jd_text)
    raw_text = complete("stress_test", prompt, max_tokens=4000)

    try:
        data = _extract_json(raw_text)
    except json.JSONDecodeError as e:
        raise StressTestParseError(f"无法解析LLM返回的JSON: {raw_text[:200]}") from e

    if not isinstance(data, list):
        raise StressTestParseError("LLM返回的结果不是一个列表")

    groups = []
    for group in data:
        if not isinstance(group, dict):
            continue
        questions = []
        for q in group.get("questions", []):
            if not isinstance(q, dict):
                continue
            questions.append(
                {
                    "question": q.get("question", ""),
                    "type": q.get("type", "其他"),
                    "why_asked": q.get("why_asked", ""),
                    "answer_guidance": q.get("answer_guidance", ""),
                }
            )
        if not questions:
            continue
        groups.append(
            {
                "experience_title": group.get("experience_title", ""),
                "questions": questions,
            }
        )

    if not groups:
        raise StressTestParseError("LLM未能生成任何有效的追问分组")

    return groups
