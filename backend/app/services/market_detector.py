import json
import re

from app.services.llm_client import complete

CHINA_KEYWORDS = [
    "户口", "社保", "五险一金", "三险一金", "应届生", "校招", "补贴",
    "工作地点", "薪资面议", "转正", "三方协议", "事业单位", "国企", "央企",
    "本科及以上", "硕士及以上", "简历投递", "招聘部门", "岗位职责", "任职要求",
    "薪资待遇", "面议", "试用期",
]

US_KEYWORDS = [
    "visa sponsorship", "opt", "cpt", "h1b", "h-1b", "green card",
    "us citizen", "equal opportunity employer", "eeo", "401(k)", "401k",
    "at-will", "relocation assistance", "background check", "w-2", "ats",
    "salary range", "remote (us)", "authorized to work in the united states",
    "e-verify", "pto", "benefits package",
]


def _chinese_char_ratio(text: str) -> float:
    if not text:
        return 0.0
    chinese_chars = re.findall(r"[一-鿿]", text)
    return len(chinese_chars) / len(text)


def score_by_keywords(jd_text: str) -> tuple[int, int]:
    lower_text = jd_text.lower()
    china_score = sum(1 for kw in CHINA_KEYWORDS if kw in jd_text)
    us_score = sum(1 for kw in US_KEYWORDS if kw in lower_text)

    if _chinese_char_ratio(jd_text) > 0.3:
        china_score += 2

    return china_score, us_score


def detect_market_with_llm(jd_text: str) -> str:
    prompt = (
        "判断以下职位描述(JD)更贴近哪个招聘市场的风格。只能回答 JSON,不要有其他文字。\n"
        '格式: {"market_style": "china"} 或 {"market_style": "us"}\n\n'
        "china = 中国大陆招聘市场风格(如提及户口、社保、五险一金、应届生校招,或整体语气、公司描述方式偏国内企业)\n"
        "us = 北美招聘市场风格(如提及 visa sponsorship、OPT/CPT、H1B、EEO,或整体语气、资质要求偏北美企业)\n\n"
        f"JD内容:\n{jd_text[:4000]}"
    )
    # 轻量模型默认会先思考再作答,max_tokens 需留出思考的空间
    text = complete("market_detect", prompt, max_tokens=1024).strip()
    try:
        data = json.loads(text)
        market_style = data.get("market_style")
    except (json.JSONDecodeError, IndexError):
        market_style = None

    if market_style not in ("china", "us"):
        return "us"
    return market_style


def detect_market_style(jd_text: str) -> tuple[str, str]:
    """Returns (suggested_market_style, method). This is only a default suggestion —
    the market_style actually used for report/generation is chosen explicitly by the caller."""
    china_score, us_score = score_by_keywords(jd_text)

    if china_score - us_score >= 2:
        return "china", "keyword"
    if us_score - china_score >= 2:
        return "us", "keyword"

    return detect_market_with_llm(jd_text), "llm"
