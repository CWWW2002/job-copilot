"""求职 Copilot 后端的命令行客户端,供 Skill 调用。只用标准库,无需安装依赖。

用法:
  python copilot.py run --resume 简历.pdf --jd jd.txt [--steps match,tailor,stress] [--market china|us]
  python copilot.py usage

后端地址默认 http://localhost:8000,可用环境变量 JOB_COPILOT_URL 覆盖
(docker compose 部署时为 http://localhost:8080)。
结果以 JSON 打印到 stdout。
"""

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE_URL = os.environ.get("JOB_COPILOT_URL", "http://localhost:8000").rstrip("/")
TIMEOUT_SECONDS = 180
ALL_STEPS = ("match", "tailor", "stress")


class CopilotError(Exception):
    pass


def _request(method: str, path: str, body: bytes | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(BASE_URL + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise CopilotError(f"{method} {path} 返回 {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise CopilotError(f"连不上后端 {BASE_URL}({e.reason}),请先启动服务") from e


def post_json(path: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return _request("POST", path, body, {"Content-Type": "application/json"})


def upload_resume(file_path: Path) -> dict:
    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        file_path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return _request("POST", "/api/resume/upload", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})


def run(resume_path: Path, jd_text: str, steps: list[str], market: str | None) -> dict:
    resume = upload_resume(resume_path)
    jd = post_json("/api/jd", {"raw_text": jd_text})
    market_style = market or jd["suggested_market_style"]
    result = {
        "resume_id": resume["id"],
        "jd_id": jd["id"],
        "market_style": market_style,
        "market_style_source": "user" if market else jd["suggestion_method"],
    }

    ids = {"resume_id": resume["id"], "jd_id": jd["id"], "market_style": market_style}
    if "match" in steps:
        result["match"] = post_json("/api/match", ids)
    if "tailor" in steps:
        result["tailor"] = post_json("/api/tailor", ids)
    if "stress" in steps:
        # 有定制简历就针对定制版追问(会带上 JD),否则针对原简历
        if "tailor" in result:
            payload = {"resume_source": "tailored", "tailored_resume_id": result["tailor"]["id"]}
        else:
            payload = {"resume_source": "original", "resume_id": resume["id"]}
        result["stress_test"] = post_json("/api/resume/stress-test", payload)
    return result


def parse_steps(raw: str) -> list[str]:
    steps = [s.strip() for s in raw.split(",") if s.strip()]
    unknown = [s for s in steps if s not in ALL_STEPS]
    if unknown or not steps:
        raise argparse.ArgumentTypeError(f"steps 只能是 {','.join(ALL_STEPS)} 的组合")
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="求职 Copilot 命令行客户端")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="上传简历和 JD,依次执行匹配 / 定制 / 压力测试")
    run_p.add_argument("--resume", required=True, type=Path, help="简历文件(PDF 或 DOCX)")
    run_p.add_argument("--jd", required=True, help="JD 文本文件路径,传 - 则从 stdin 读取")
    run_p.add_argument("--steps", default=",".join(ALL_STEPS), type=parse_steps)
    run_p.add_argument("--market", choices=["china", "us"], help="不传则采用后端的自动识别结果")

    sub.add_parser("usage", help="查看按任务 / 模型的 LLM 成本统计")

    args = parser.parse_args(argv)
    try:
        if args.command == "usage":
            output = _request("GET", "/api/usage")
        else:
            jd_text = sys.stdin.read() if args.jd == "-" else Path(args.jd).read_text(encoding="utf-8")
            output = run(args.resume, jd_text, args.steps, args.market)
    except CopilotError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
