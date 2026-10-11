"""job-copilot Skill 脚本的测试:门槛预检规则,以及命令行客户端走通真实 API(LLM 全部 mock)。"""

import importlib.util
import io
import json
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.main import app

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "job-copilot" / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


precheck = _load("precheck")
copilot = _load("copilot")

CHINA_JD = "岗位职责:负责 AI 产品需求分析。任职要求:本科及以上,应届生校招,五险一金,工作地点深圳,熟悉 Python。"


def test_precheck_flags_hard_school_filter():
    findings = precheck.precheck("任职要求:985 或 QS 前 100 院校硕士及以上学历;英语六级。")

    by_category = {f["category"]: f for f in findings}
    assert by_category["学校层次"]["level"] == "hard"
    assert {f["keyword"] for f in findings if f["category"] == "学校层次"} == {"985", "QS 前 100"}
    assert "学历" in by_category and "语言证书" in by_category


def test_precheck_marks_preferred_as_soft():
    findings = precheck.precheck("本科及以上学历;持有 PMP 等项目管理认证者优先。")

    assert [(f["category"], f["level"]) for f in findings] == [("证书", "soft")]


def test_precheck_soft_marker_does_not_leak_across_sentences():
    """前一句的"优先"不能让后一句的硬门槛变成软条件。"""
    findings = precheck.precheck("计算机专业优先。须为 985 院校毕业。")

    assert [(f["keyword"], f["level"]) for f in findings] == [("985", "hard")]


def test_precheck_no_findings_for_plain_jd():
    assert precheck.precheck("负责产品需求分析与版本规划,本科及以上学历。") == []


@pytest.fixture
def api(monkeypatch):
    """把客户端的 HTTP 请求转发给 TestClient,并 mock 掉三个 LLM 生成函数。"""
    client = TestClient(app)

    def fake_request(method, path, body=None, headers=None):
        resp = client.request(method, path, content=body, headers=headers or {})
        if resp.status_code >= 400:
            raise copilot.CopilotError(f"{method} {path} 返回 {resp.status_code}: {resp.text}")
        return resp.json()

    monkeypatch.setattr(copilot, "_request", fake_request)
    monkeypatch.setattr(
        "app.routers.match.generate_match_report",
        lambda resume, jd, style: {
            "score": 80, "matched_skills": ["Python"], "missing_skills": ["Axure"],
            "summary_zh": "匹配", "summary_en": "match",
        },
    )
    monkeypatch.setattr("app.routers.tailor.generate_tailored_resume", lambda resume, jd, style: "# 定制简历")
    stress_calls = []

    def fake_stress(resume_text, jd_text):
        stress_calls.append((resume_text, jd_text))
        return [{"experience": "实习", "questions": []}]

    monkeypatch.setattr("app.routers.stress_test.generate_stress_test", fake_stress)
    return stress_calls


@pytest.fixture
def resume_file(tmp_path):
    path = tmp_path / "resume.docx"
    doc = Document()
    doc.add_paragraph("张三 软件工程 本科 熟悉 Python 与 SQL,做过 AI 产品实习")
    doc.save(path)
    return path


def test_run_all_steps_through_api(api, resume_file):
    result = copilot.run(resume_file, CHINA_JD, ["match", "tailor", "stress"], market=None)

    # 市场风格采用后端的关键词识别结果
    assert result["market_style"] == "china"
    assert result["market_style_source"] == "keyword"
    assert result["match"]["score"] == 80
    assert result["tailor"]["content"] == "# 定制简历"
    # 有定制简历时,压力测试针对定制版并带上 JD
    assert result["stress_test"]["resume_source"] == "tailored"
    assert api == [("# 定制简历", CHINA_JD)]


def test_run_stress_only_uses_original_resume(api, resume_file):
    result = copilot.run(resume_file, CHINA_JD, ["stress"], market="us")

    assert "match" not in result and "tailor" not in result
    assert result["market_style"] == "us" and result["market_style_source"] == "user"
    assert result["stress_test"]["resume_source"] == "original"
    assert "张三" in api[0][0] and api[0][1] is None


def test_cli_reports_error_and_exit_code(api, tmp_path, monkeypatch, capsys):
    bad = tmp_path / "resume.txt"
    bad.write_text("不是 PDF")
    monkeypatch.setattr("sys.stdin", io.StringIO(CHINA_JD))

    code = copilot.main(["run", "--resume", str(bad), "--jd", "-", "--steps", "match"])

    assert code == 1
    assert "400" in json.loads(capsys.readouterr().err)["error"]


def test_parse_steps_rejects_unknown():
    assert copilot.parse_steps("match, stress") == ["match", "stress"]
    with pytest.raises(Exception):
        copilot.parse_steps("match,deploy")
