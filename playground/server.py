"""Jev Playground —— 本地可视化调试台

用法：
    .venv/bin/python playground/server.py
然后浏览器打开 http://127.0.0.1:8777

只监听 127.0.0.1，API key 保存在服务端进程里，不会发到浏览器。
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from typesafe_sdk import (
    Choice,
    Noul,
    Score,
    TypeSafeClient,
    TypeSafeError,
)

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
STATIC = ROOT / "static"

load_dotenv(PROJECT / ".env")

_client: TypeSafeClient | None = None


def get_client() -> TypeSafeClient:
    """懒加载：没配 key 时也能起服务，调用时才报错。"""
    global _client
    if _client is None:
        _client = TypeSafeClient()
    return _client


class BadInput(Exception):
    """前端传参有问题，返回 400 而不是 500。"""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def build_questions(raw: Any) -> dict[str, Any]:
    """把前端发来的问题数组转成 SDK 的 Choice / Score / Noul 对象。"""
    if not isinstance(raw, list) or not raw:
        raise BadInput("至少需要一个问题")

    questions: dict[str, Any] = {}
    for idx, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise BadInput(f"第 {idx} 个问题格式不对")
        name = _clean(item.get("name"))
        if not name:
            raise BadInput(f"第 {idx} 个问题缺少 name（问题名只用于你自己取结果，不会发给模型）")
        if name in questions:
            raise BadInput(f"问题名重复：{name}")

        qtype = item.get("type")
        instructions = _clean(item.get("instructions")) or None

        if qtype == "choice":
            criteria = item.get("criteria") or {}
            cleaned = {_clean(k): (_clean(v) or None) for k, v in criteria.items() if _clean(k)}
            if len(cleaned) < 2:
                raise BadInput(f"Choice「{name}」至少需要 2 个选项")
            if len(cleaned) > 255:
                raise BadInput(f"Choice「{name}」最多 255 个选项")
            questions[name] = Choice(instructions=instructions, criteria=cleaned)

        elif qtype == "score":
            levels = [_clean(v) for v in (item.get("criteria") or [])]
            levels = [v for v in levels if v]
            if len(levels) < 2:
                raise BadInput(f"Score「{name}」至少需要 2 个等级")
            if len(levels) > 10:
                raise BadInput(f"Score「{name}」最多 10 个等级")
            questions[name] = Score(instructions=instructions, criteria=levels)

        elif qtype == "noul":
            criteria = None
            raw_criteria = item.get("criteria") or {}
            if isinstance(raw_criteria, dict):
                yes, no = _clean(raw_criteria.get("true")), _clean(raw_criteria.get("false"))
                if yes or no:
                    criteria = {}
                    if yes:
                        criteria["true"] = yes
                    if no:
                        criteria["false"] = no
            questions[name] = Noul(instructions=instructions, criteria=criteria)

        else:
            raise BadInput(f"第 {idx} 个问题的 type 无法识别：{qtype!r}")

    return questions


def build_state(payload: dict[str, Any]) -> Any:
    mode = payload.get("state_mode", "text")
    text = payload.get("state_text") or ""
    if mode == "json":
        if not text.strip():
            raise BadInput("state 为空")
        try:
            state = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BadInput(f"state 不是合法 JSON：{exc.msg}（第 {exc.lineno} 行第 {exc.colno} 列）") from exc
    else:
        state = text
    if isinstance(state, str) and not state.strip():
        raise BadInput("state 不能为空")
    return state


def apply_rule_pack(state: Any, rule_text: str, rule_mode: str) -> tuple[Any, list[str]]:
    """把「常驻规则」合并进 state —— 这是 Jev 版的 system prompt 替代品。

    Jev 没有 system 字段（塞了会 400），也没有跨调用记忆，所以规则必须每次随 state 一起送。

    合并策略：
      · state 是 JSON 对象 + 规则是 JSON 对象 → 直接合并（state 的键优先，冲突键会回报给前端）
      · state 是 JSON 对象 + 规则是文本       → 规则挂到 `rules` 键下
      · state 是文本                         → 规则拼在正文前面，加标题分隔
    """
    if not rule_text.strip():
        return state, []

    if rule_mode == "json":
        try:
            rule: Any = json.loads(rule_text)
        except json.JSONDecodeError as exc:
            raise BadInput(
                f"常驻规则不是合法 JSON：{exc.msg}（第 {exc.lineno} 行第 {exc.colno} 列）"
                "；如果只想写一段文字，请把上方切到「纯文本」"
            ) from exc
    else:
        rule = rule_text.strip()

    if isinstance(state, dict):
        if isinstance(rule, dict):
            conflicts = sorted(set(rule) & set(state))
            return {**rule, **state}, conflicts  # state 优先
        return {"rules": rule, **state}, []

    rule_as_text = rule if isinstance(rule, str) else json.dumps(rule, ensure_ascii=False, indent=2)
    return f"【内部规则 / rules】\n{rule_as_text}\n\n【待判断内容 / content】\n{state}", []


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "JevPlayground"

    # ---------- 响应工具 ----------

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, obj: Any, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def send_file(self, rel: str) -> None:
        target = (STATIC / rel.lstrip("/")).resolve()
        if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
        }.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)

    def read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise BadInput("请求体为空")
        try:
            payload = json.loads(self.rfile.read(length).decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BadInput(f"请求体不是合法 JSON：{exc}") from exc
        if not isinstance(payload, dict):
            raise BadInput("请求体必须是 JSON 对象")
        return payload

    # ---------- 路由 ----------

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path == "/api/models":
            try:
                resp = get_client().models.list()
                self.send_json({"ok": True, "models": [
                    {"name": m.name, "description": m.description, "release_date": m.release_date}
                    for m in resp.models
                ]})
            except TypeSafeError as exc:
                self.send_json({"ok": False, "error": _describe(exc)}, 400)
            return

        if path == "/":
            path = "/index.html"
        self.send_file(path)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/api/evaluate":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        try:
            payload = self.read_body()
            state = build_state(payload)
            questions = build_questions(payload.get("questions"))

            # 常驻规则：前端可以用同一个 state 分别跑「带规则」和「不带规则」做对照
            if payload.get("use_rule_pack", True):
                state, conflicts = apply_rule_pack(
                    state,
                    str(payload.get("rule_pack_text") or ""),
                    payload.get("rule_pack_mode", "json"),
                )
            else:
                conflicts = []

            started = time.perf_counter()
            resp = get_client().system_one(state=state, questions=questions)
            elapsed_ms = (time.perf_counter() - started) * 1000

            data = resp.model_dump(mode="json")
            self.send_json({
                "ok": True,
                "elapsed_ms": round(elapsed_ms),
                "model": data.get("model"),
                "usage": data.get("usage") or {},
                "answers": data.get("answers") or {},
                # 回传实际发出去的 state 和问题定义，方便前端做「查看实际请求」调试
                "sent_state": state,
                "rule_conflicts": conflicts,
            })
        except BadInput as exc:
            self.send_json({"ok": False, "error": str(exc)}, 400)
        except TypeSafeError as exc:
            self.send_json({"ok": False, "error": _describe(exc)}, 502)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": f"服务端异常：{type(exc).__name__}: {exc}"}, 500)

    def log_message(self, fmt: str, *args: Any) -> None:
        # 非 tty 下 stdout 会缓冲，加 flush 让请求日志实时可见
        print(f"  {self.address_string()} {fmt % args}", flush=True)


def _describe(exc: TypeSafeError) -> str:
    name = type(exc).__name__
    if "Authentication" in name:
        return "认证失败：TYPESAFE_API_KEY 不对或已失效（检查 .env）"
    if "RateLimit" in name:
        return f"触发限流，稍后重试：{exc}"
    return f"{name}: {exc}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev Playground 本地服务")
    parser.add_argument("--port", type=int, default=8777)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"\n  Jev Playground 已启动 →  http://127.0.0.1:{args.port}", flush=True)
    print("  只监听本机；Ctrl+C 退出\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止", flush=True)
    finally:
        server.server_close()
        if _client is not None:
            _client.close()


if __name__ == "__main__":
    main()
