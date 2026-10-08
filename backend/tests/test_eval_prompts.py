"""幻觉率测试的对照组 prompt 必须与线上 prompt 保持预期差异,否则评测结果失去意义。"""

from app.services.tailor_service import build_tailor_prompt
from evals.hallucination_eval import build_baseline_prompt, build_v1_prompt, new_numbers


def test_v1_prompt_only_drops_rules_6_to_8():
    current = build_tailor_prompt("简历", "JD", "china")
    v1 = build_v1_prompt("简历", "JD", "china")

    assert "6. 保留原文对个人角色的界定" in current
    assert "6. 保留原文" not in v1 and "8. 如果生成个人总结" not in v1
    assert "5. 如果用户过往经历" in v1  # 其余规则保留


def test_baseline_prompt_has_no_anti_fabrication_rules():
    baseline = build_baseline_prompt("简历", "JD", "us")

    assert "绝对不能编造" not in baseline


def test_new_numbers_ignores_reformatted_dates_and_list_markers():
    original = "2024-09 ~ 2025-04,延迟降低 35%"
    tailored = "1. 2024.09 - 2025.04,延迟降低 35%,新增用户 8000+"

    assert new_numbers(original, tailored) == ["8000"]
