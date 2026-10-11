"""JD 硬性门槛预检:在定制简历之前,用规则找出可能直接淘汰候选人的条件。

只做规则匹配,不调用 LLM。命中项交给用户确认,脚本本身不判断用户是否满足。

用法: python precheck.py <jd.txt>      (或从 stdin 读入 JD)
输出: JSON 列表,每项包含 category / keyword / context
"""

import json
import re
import sys

# 类别 -> 关键词正则。只收录"不满足就会被筛掉"的硬条件,"优先""加分"类表述单独标记为软条件。
HARD_FILTER_PATTERNS = {
    "学校层次": [r"985", r"211", r"双一流", r"知名院校", r"名校", r"QS\s*(?:前|top)?\s*\d+", r"世界排名前\s*\d+"],
    "学历": [r"(?:博士|硕士)(?:研究生)?及以上", r"全日制"],
    "毕业时间": [r"20\d{2}\s*年?\s*\d{1,2}\s*月\s*(?:\d{1,2}\s*日)?\s*(?:前|之前|以前)\s*毕业", r"\d{2}\s*届"],
    "留学认证": [r"留服认证", r"学历认证", r"学位认证"],
    "语言证书": [r"CET-?[46]", r"英语[四六]级", r"雅思\s*\d", r"托福\s*\d", r"TEM-?[48]"],
    "证书": [r"PMP", r"ACP", r"CPA", r"CFA", r"FRM", r"法律职业资格"],
    "身份与工作授权": [r"户口", r"户籍", r"visa sponsorship", r"work authorization", r"authorized to work"],
}

SOFT_MARKERS = ("优先", "加分", "preferred", "plus", "nice to have")

CONTEXT_CHARS = 25


def _soft(context: str) -> bool:
    lower = context.lower()
    return any(marker in lower for marker in SOFT_MARKERS)


def precheck(jd_text: str) -> list[dict]:
    findings = []
    seen = set()
    for category, patterns in HARD_FILTER_PATTERNS.items():
        for pattern in patterns:
            for m in re.finditer(pattern, jd_text, flags=re.IGNORECASE):
                start = max(0, m.start() - CONTEXT_CHARS)
                end = min(len(jd_text), m.end() + CONTEXT_CHARS)
                # 上下文截到所在句子,避免把相邻句子的"优先"算进来
                context = re.split(r"[;；。\n]", jd_text[start:end])
                sentence = next((s for s in context if m.group(0) in s), jd_text[start:end]).strip()
                key = (category, m.group(0).lower(), sentence)
                if key in seen:
                    continue
                seen.add(key)
                findings.append({
                    "category": category,
                    "keyword": m.group(0),
                    "level": "soft" if _soft(sentence) else "hard",
                    "context": sentence,
                })
    return findings


def main() -> None:
    text = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    print(json.dumps(precheck(text), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
