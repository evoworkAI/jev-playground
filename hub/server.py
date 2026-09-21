"""Jev 演示中心 —— 一个端口装下所有 demo

跑法：
    python3 hub/server.py              # 纯标准库，系统 python3 直接能跑
    python3 hub/server.py --port 8800

然后浏览器打开 http://127.0.0.1:8800

页面结构
    /                 门户页：总览 / 吃豆人 / 内容审核 / 简历筛选 / 空白模板
    /pacman/          吃豆人 AI 决策实测（iframe 嵌入，带 ?embed=1 隐藏自身页头）
    /playground/      原来的完整调试台，仍然可以单独访问（不在 tab 里）
    /zh/*             简繁切换器（zh.js / zh.css / OpenCC 词表），三个页面共用

    后三个 tab（内容审核 / 简历筛选 / 空白模板）是门户页里原生的工作台，
    共用下面这一个接口：
        POST /hub/api/evaluate   和 playground 的 /api/evaluate 同一个协议

为什么简繁切换挂在 /zh/ 而不是各自页面目录下
    三个页面用同一个相对写法 ../zh/ 引用它：门户页在根目录、吃豆人页在 /pacman/、
    调试台在 /playground/，三者上一级都正好落到 /zh/。吃豆人页因此既能在门户页里
    被嵌入，也能被 pacman_demo/server.py 单独起在根目录，不用改一行路径。
    切换状态存在 localStorage（同源共享），所以门户页切一下，iframe 和另开的
    调试台标签页会跟着一起变 —— 靠浏览器派发的 storage 事件，不需要 postMessage。

为什么要有这个「中心」
    以前每个 demo 各自一个 server.py、各自一个端口（playground 8777、吃豆人 8791），
    演示时要开好几个终端、记好几个地址。现在收进一个进程、一个端口。
    吃豆人页是被「装」进来的：把它的 fetch 路径改成相对路径后，挂在 /pacman/ 下
    自然解析成 /pacman/api/*，而它自己的 server.py 单独跑时仍然解析成 /api/*，
    所以 pacman_demo/server.py 一行没动，照样能独立启动。

为什么不用 SDK
    playground/server.py 用的是 typesafe_sdk，得跑在 .venv 里。
    这里直接按线上协议说 JSON —— 协议就三个字段（state / model / questions），
    每种问题就是 type + instructions + criteria，自己拼完全够用，
    于是整个中心只依赖标准库，python3 hub/server.py 就能起。
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from paths import resolve, runtime_root

_P = resolve()
HERE = _P["HERE"]
PROJECT = _P["PROJECT"]
STATIC = _P["STATIC"]
PLAYGROUND = _P["PLAYGROUND"]
PACMAN_INDEX = _P["PACMAN_INDEX"]
ZH_ASSETS = _P["ZH_ASSETS"]
ENV_FILE = _P["ENV_FILE"]
ENV_EXAMPLE = _P["ENV_EXAMPLE"]

DEFAULT_JEV_BASE = "https://api.typesafe.ai"
DEFAULT_LLM_BASE = "https://api.openai.com/v1"
DEFAULT_JEV_MODEL = "jev-latest"
DEFAULT_LLM_MODEL = "gpt-4o-mini"

UPSTREAM_TIMEOUT = 120.0


# --------------------------------------------------------------------------
# SSL：macOS 上系统 python3 经常找不到根证书，导致 CERTIFICATE_VERIFY_FAILED。
# 优先用 truststore（走 Keychain），退而求其次用 certifi，最后退回系统证书包。
# 与 pacman_demo/server.py 保持一致。
# --------------------------------------------------------------------------
def build_ssl_context() -> ssl.SSLContext | None:
    try:
        import truststore  # type: ignore[import-not-found]

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        pass

    try:
        import certifi  # type: ignore[import-not-found]

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    for bundle in ("/etc/ssl/cert.pem", "/usr/local/etc/openssl/cert.pem"):
        if Path(bundle).exists():
            return ssl.create_default_context(cafile=bundle)

    return None


SSL_CONTEXT = build_ssl_context()


# --------------------------------------------------------------------------
# .env 读取（不依赖 python-dotenv，系统 python3 直接能跑）
# --------------------------------------------------------------------------
def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


ENV = load_env(ENV_FILE)

JEV_BASE = (ENV.get("TYPESAFE_BASE_URL") or DEFAULT_JEV_BASE).rstrip("/")
JEV_MODEL = ENV.get("TYPESAFE_DEFAULT_MODEL", "").strip() or DEFAULT_JEV_MODEL
JEV_KEY = ENV.get("TYPESAFE_API_KEY", "").strip()


def mask(key: str) -> str:
    """只回显 key 的尾巴，避免把完整密钥发给前端。"""
    if not key:
        return ""
    return f"{key[:12]}…{key[-4:]}" if len(key) > 20 else "已配置"


# --------------------------------------------------------------------------
# 上游调用
# --------------------------------------------------------------------------
def call_upstream(url: str, api_key: str, payload: dict | None, method: str = "POST") -> dict:
    """转发一次请求。永远返回 dict，不抛异常，让前端能拿到可读的错误。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT, context=SSL_CONTEXT) as resp:
            body = resp.read().decode("utf-8", "replace")
            latency = (time.perf_counter() - started) * 1000
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"raw": body[:2000]}
            return {"ok": True, "status": resp.status, "latencyMs": round(latency, 1), "data": parsed}

    except urllib.error.HTTPError as exc:
        latency = (time.perf_counter() - started) * 1000
        detail = exc.read().decode("utf-8", "replace")[:4000]
        try:
            detail = json.loads(detail)
        except json.JSONDecodeError:
            pass
        return {"ok": False, "status": exc.code, "latencyMs": round(latency, 1), "error": detail}

    except urllib.error.URLError as exc:
        return {"ok": False, "status": 0, "latencyMs": round((time.perf_counter() - started) * 1000, 1),
                "error": f"连接失败: {exc.reason}"}

    except Exception as exc:  # noqa: BLE001 - 兜底，调试阶段要看到真实原因
        return {"ok": False, "status": 0, "latencyMs": round((time.perf_counter() - started) * 1000, 1),
                "error": f"{type(exc).__name__}: {exc}"}


def describe_error(err: Any) -> str:
    if isinstance(err, dict):
        detail = err.get("detail")
        if isinstance(detail, list) and detail:
            first = detail[0]
            loc = ".".join(str(x) for x in (first.get("loc") or []))
            return f"{first.get('msg', '参数错误')}（{loc}）"
        if isinstance(detail, str):
            return detail
        # 上游有些错误把 detail 也做成对象，例如
        # {"detail": {"error_type": "api_usage_error", "message": "Invalid request."}}
        if isinstance(detail, dict):
            if detail.get("message"):
                etype = detail.get("error_type")
                return f"{detail['message']}（{etype}）" if etype else str(detail["message"])
            return json.dumps(detail, ensure_ascii=False)
        if "error" in err:
            inner = err["error"]
            if isinstance(inner, dict):
                return str(inner.get("message") or inner)
            return str(inner)
    return str(err)


# --------------------------------------------------------------------------
# 问题的 JSON 拼装
#   Jev 的问题就三种，线上协议直接写 JSON 即可，不必经过 SDK 的类：
#     Choice → criteria 是 {选项名: 说明}，说明可以为空（null）
#     Score  → criteria 是 [等级0说明, 等级1说明, ...]，位置即分数
#     Noul   → criteria 可选，写清什么算 true / 什么算 false
# --------------------------------------------------------------------------
def Q_choice(instructions: str | None, criteria: dict[str, str | None]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def Q_score(instructions: str | None, levels: list[str]) -> dict:
    return {"type": "score", "instructions": instructions, "criteria": levels}


def Q_noul(instructions: str | None, criteria: dict[str, str] | None = None) -> dict:
    q: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if criteria:
        q["criteria"] = criteria
    return q


# ==========================================================================
# 工作台的核心接口：和 playground 的 /api/evaluate 同一个协议
#
# 合并常驻规则（Jev 没有 system 字段，规则只能塞进 state）：
#   · state 是 JSON 对象 + 规则是 JSON 对象 → 直接合并，state 的键优先
#   · state 是 JSON 对象 + 规则是文本      → 规则挂到 `rules` 键下
#   · state 是文本                         → 规则拼在正文前面
# ==========================================================================
def build_state(payload: dict) -> Any:
    mode = payload.get("state_mode", "text")
    text = payload.get("state_text") or ""
    if mode == "json":
        if not text.strip():
            raise ValueError("state 为空")
        try:
            state = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"state 不是合法 JSON：{exc.msg}（第 {exc.lineno} 行第 {exc.colno} 列）") from exc
    else:
        state = text
    if isinstance(state, str) and not state.strip():
        raise ValueError("state 不能为空")
    return state


def build_questions(raw: Any) -> dict:
    if not isinstance(raw, list) or not raw:
        raise ValueError("至少需要一个问题")

    questions: dict[str, Any] = {}
    for idx, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {idx} 个问题格式不对")
        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError(f"第 {idx} 个问题缺少名字（问题名只用于取结果，不会发给模型）")
        if name in questions:
            raise ValueError(f"问题名重复：{name}")

        qtype = item.get("type")
        instructions = str(item.get("instructions") or "").strip() or None

        if qtype == "choice":
            criteria = item.get("criteria") or {}
            if not isinstance(criteria, dict):
                raise ValueError(f"Choice「{name}」的 criteria 必须是对象")
            cleaned = {str(k).strip(): (str(v).strip() or None)
                       for k, v in criteria.items() if str(k).strip()}
            if len(cleaned) < 2:
                raise ValueError(f"Choice「{name}」至少需要 2 个选项")
            if len(cleaned) > 255:
                raise ValueError(f"Choice「{name}」最多 255 个选项")
            questions[name] = Q_choice(instructions, cleaned)

        elif qtype == "score":
            levels = [str(v).strip() for v in (item.get("criteria") or [])]
            levels = [v for v in levels if v]
            if len(levels) < 2:
                raise ValueError(f"Score「{name}」至少需要 2 个等级")
            if len(levels) > 10:
                raise ValueError(f"Score「{name}」最多 10 个等级")
            questions[name] = Q_score(instructions, levels)

        elif qtype == "noul":
            criteria = None
            raw_criteria = item.get("criteria") or {}
            if isinstance(raw_criteria, dict):
                yes = str(raw_criteria.get("true") or "").strip()
                no = str(raw_criteria.get("false") or "").strip()
                if yes or no:
                    criteria = {}
                    if yes:
                        criteria["true"] = yes
                    if no:
                        criteria["false"] = no
            questions[name] = Q_noul(instructions, criteria)

        else:
            raise ValueError(f"第 {idx} 个问题的 type 无法识别：{qtype!r}")

    return questions


def apply_rule_pack(state: Any, rule_text: str, rule_mode: str) -> tuple[Any, list[str]]:
    if not rule_text.strip():
        return state, []

    if rule_mode == "json":
        try:
            rule: Any = json.loads(rule_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"常驻规则不是合法 JSON：{exc.msg}（第 {exc.lineno} 行第 {exc.colno} 列）"
                "；如果只想写一段文字，请把上方切到「纯文本」") from exc
    else:
        rule = rule_text.strip()

    if isinstance(state, dict):
        if isinstance(rule, dict):
            conflicts = sorted(set(rule) & set(state))
            return {**rule, **state}, conflicts  # state 优先
        return {"rules": rule, **state}, []

    rule_as_text = rule if isinstance(rule, str) else json.dumps(rule, ensure_ascii=False, indent=2)
    return f"【内部规则 / rules】\n{rule_as_text}\n\n【待判断内容 / content】\n{state}", []


def handle_evaluate(payload: dict) -> tuple[dict, int]:
    try:
        state = build_state(payload)
        questions = build_questions(payload.get("questions"))
        conflicts: list[str] = []
        if payload.get("use_rule_pack", True):
            state, conflicts = apply_rule_pack(
                state, str(payload.get("rule_pack_text") or ""),
                payload.get("rule_pack_mode", "json"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}, 400

    res = call_upstream(f"{JEV_BASE}/v1/systemone", JEV_KEY,
                        {"state": state, "model": JEV_MODEL, "questions": questions})
    if not res["ok"]:
        return {"ok": False, "error": describe_error(res.get("error"))}, 502

    data = res["data"]
    return {
        "ok": True,
        "elapsed_ms": round(res["latencyMs"]),
        "model": data.get("model"),
        "usage": data.get("usage") or {},
        "answers": data.get("answers") or {},
        # 回传实际发出去的 state，用户可以点「查看实际请求」确认规则合并对不对
        "sent_state": state,
        "rule_conflicts": conflicts,
    }, 200


# ==========================================================================
# 吃豆人的三个代理（保持它原来的 {ok,status,latencyMs,data} 形态）
# ==========================================================================
def normalize_base(url: str, fallback: str) -> str:
    base = (url or "").strip().rstrip("/") or fallback
    if not re.match(r"^https?://", base):
        raise ValueError("base url 必须以 http:// 或 https:// 开头")
    return base


def handle_pacman_jev(body: dict) -> dict:
    base = normalize_base(body.get("baseUrl", ""), DEFAULT_JEV_BASE)
    payload = {
        "state": body.get("state"),
        "model": body.get("model") or JEV_MODEL,
        "questions": body.get("questions"),
    }
    key = (body.get("apiKey") or "").strip() or JEV_KEY
    return call_upstream(f"{base}/v1/systemone", key, payload)


def handle_pacman_llm(body: dict) -> dict:
    base = normalize_base(body.get("baseUrl", ""), DEFAULT_LLM_BASE)
    payload = {
        "model": body.get("model") or DEFAULT_LLM_MODEL,
        "messages": body.get("messages") or [],
        "temperature": body.get("temperature", 0),
        "max_tokens": body.get("maxTokens", 16),
    }
    if body.get("jsonMode", True):
        payload["response_format"] = {"type": "json_object"}
    key = (body.get("apiKey") or "").strip() or (ENV.get("LLM_API_KEY") or ENV.get("OPENAI_API_KEY") or "").strip()
    return call_upstream(f"{base}/chat/completions", key, payload)


def handle_pacman_models(body: dict) -> dict:
    if body.get("provider", "jev") == "jev":
        base = normalize_base(body.get("baseUrl", ""), DEFAULT_JEV_BASE)
        key = (body.get("apiKey") or "").strip() or JEV_KEY
        return call_upstream(f"{base}/v1/models", key, None, method="GET")
    base = normalize_base(body.get("baseUrl", ""), DEFAULT_LLM_BASE)
    key = (body.get("apiKey") or "").strip() or (ENV.get("LLM_API_KEY") or ENV.get("OPENAI_API_KEY") or "").strip()
    return call_upstream(f"{base}/models", key, None, method="GET")


def handle_pacman_config() -> dict:
    """吃豆人页面预填用的默认值。key 只回显掩码，真实 key 留在服务端。"""
    return {
        "ok": True, "status": 200,
        "data": {
            "jev": {
                "baseUrl": ENV.get("TYPESAFE_BASE_URL", "").strip() or DEFAULT_JEV_BASE,
                "model": JEV_MODEL,
                "hasKey": bool(JEV_KEY),
                "keyHint": mask(JEV_KEY),
            },
            "llm": {
                "baseUrl": ENV.get("LLM_BASE_URL", "").strip() or DEFAULT_LLM_BASE,
                "model": ENV.get("LLM_MODEL", "").strip() or DEFAULT_LLM_MODEL,
                "hasKey": bool(ENV.get("LLM_API_KEY") or ENV.get("OPENAI_API_KEY")),
                "keyHint": mask(ENV.get("LLM_API_KEY") or ENV.get("OPENAI_API_KEY") or ""),
            },
        },
    }


def hub_meta() -> dict:
    """门户页开头需要的环境信息。"""
    return {
        "ok": True,
        "model": JEV_MODEL,
        "base": JEV_BASE,
        "hasKey": bool(JEV_KEY),
        "keyHint": mask(JEV_KEY),
        "envFile": str(ENV_FILE),
    }


# ==========================================================================
# 静态文件与路由
# ==========================================================================
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def safe_join(root: Path, rel: str) -> Path | None:
    """把 rel 拼到 root 下，并挡掉 ../ 穿越。"""
    target = (root / rel.lstrip("/")).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "JevDemoHub/1.0"

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
        self._send(status, json.dumps(obj, ensure_ascii=False).encode(),
                   "application/json; charset=utf-8")

    def send_redirect(self, to: str) -> None:
        """子路径必须以斜杠结尾，否则页面里的相对路径会解析歪。"""
        self.send_response(301)
        self.send_header("Location", to)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_root_file(self, root: Path, rel: str) -> None:
        target = safe_join(root, rel)
        if target is None or not target.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        self._send(200, target.read_bytes(),
                   MIME.get(target.suffix, "application/octet-stream"))

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    # ---------- GET ----------
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        rel = path.lstrip("/")

        # 门户页
        if path == "/":
            self.send_root_file(STATIC, "index.html")
            return
        if rel in ("hub.css", "hub.js", "favicon.svg"):
            self.send_root_file(STATIC, rel)
            return

        # 简繁切换器。挂在 /zh/ 这个固定位置，是为了让三个页面用同一个
        # 相对写法（../zh/zh.js）都能解析到它 —— 吃豆人页被门户页装在
        # /pacman/ 下、自己单跑时在根目录，两种情况下 ../zh/ 都落到 /zh/。
        if rel.startswith("zh/"):
            self.send_root_file(ZH_ASSETS, rel[len("zh/"):])
            return

        # 吃豆人（iframe 嵌入；?embed=1 由页面自己处理）
        if path == "/pacman":
            self.send_redirect("/pacman/")
            return
        if path in ("/pacman/", "/pacman/index.html"):
            if not PACMAN_INDEX.is_file():
                self._send(404, b"pacman index.html not found", "text/plain; charset=utf-8")
                return
            self._send(200, PACMAN_INDEX.read_bytes(), MIME[".html"])
            return
        if rel == "pacman/api/config":
            self.send_json(handle_pacman_config())
            return

        # Jev Playground：不再是 tab，但页面还留着，可以单独访问
        if path == "/playground":
            self.send_redirect("/playground/")
            return
        if path in ("/playground/", "/playground/index.html"):
            self.send_root_file(PLAYGROUND, "index.html")
            return
        if rel.startswith("playground/"):
            sub = rel[len("playground/"):]
            if sub == "api/models":
                self.handle_playground_models()
                return
            self.send_root_file(PLAYGROUND, sub)
            return

        if rel == "hub/api/meta":
            self.send_json(hub_meta())
            return
        if rel == "hub/api/models":
            self.handle_playground_models()
            return

        self._send(404, b"not found", "text/plain; charset=utf-8")

    # ---------- POST ----------
    def do_POST(self) -> None:  # noqa: N802
        rel = self.path.split("?", 1)[0].lstrip("/")
        body = self.read_body()

        # 工作台
        if rel in ("hub/api/evaluate", "api/evaluate", "playground/api/evaluate"):
            self.send_json(*handle_evaluate(body))
            return

        # 吃豆人的代理
        if rel == "pacman/api/jev":
            self.send_json(handle_pacman_jev(body))
            return
        if rel == "pacman/api/llm":
            self.send_json(handle_pacman_llm(body))
            return
        if rel == "pacman/api/models":
            self.send_json(handle_pacman_models(body))
            return

        self.send_json({"ok": False, "error": "unknown route"}, 404)

    def handle_playground_models(self) -> None:
        res = call_upstream(f"{JEV_BASE}/v1/models", JEV_KEY, None, method="GET")
        if not res["ok"]:
            self.send_json({"ok": False, "error": describe_error(res.get("error"))}, 400)
            return
        self.send_json({"ok": True, "models": (res["data"] or {}).get("models") or []})

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A002
        # 只打一行简版日志，别把 body 打出来（里面可能带 key）
        print(f"  {self.address_string()} {fmt % args}", flush=True)


# --------------------------------------------------------------------------
# 启动
# --------------------------------------------------------------------------
BANNER = """
==============================================================================
  Jev 演示中心
==============================================================================
  .env 配置     : {env}  ({env_state})
  Jev base url  : {base}
  Jev model     : {model}
  Jev key       : {key}
------------------------------------------------------------------------------
  打开：http://{host}:{port}
    tab 1 总览        tab 2 吃豆人      tab 3 内容审核
    tab 4 简历筛选    tab 5 空白模板
------------------------------------------------------------------------------
  注意：一定从这个地址进。直接双击 HTML（file://）会调不到 /api/*。
  Ctrl-C 退出
==============================================================================
"""


def ensure_env_file() -> None:
    """打包版首次运行：在 exe/.app 旁边生成 .env（从模板复制）。"""
    if ENV_FILE.exists():
        return
    if ENV_EXAMPLE.is_file():
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  ✓ 已在 {ENV_FILE} 创建配置文件（可选，填 key 后 AI 功能才可用）", flush=True)


def open_browser_later(host: str, port: int, delay: float = 1.0) -> None:
    url = f"http://{host}:{port}/"

    def _go() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except OSError:
            pass

    threading.Thread(target=_go, daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev 演示中心 —— 一个端口装下所有 demo")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    args = parser.parse_args()

    # 打包版默认自动开浏览器；开发模式用启动脚本控制
    if args.open or getattr(sys, "frozen", False):
        open_browser_later(args.host, args.port)

    if getattr(sys, "frozen", False):
        ensure_env_file()
        # .env 可能在 ensure 之后才创建，重新读一遍
        global ENV, JEV_KEY, JEV_BASE, JEV_MODEL  # noqa: PLW0603
        ENV = load_env(ENV_FILE)
        JEV_BASE = (ENV.get("TYPESAFE_BASE_URL") or DEFAULT_JEV_BASE).rstrip("/")
        JEV_MODEL = ENV.get("TYPESAFE_DEFAULT_MODEL", "").strip() or DEFAULT_JEV_MODEL
        JEV_KEY = ENV.get("TYPESAFE_API_KEY", "").strip()

    mode = "独立程序" if getattr(sys, "frozen", False) else "Python 脚本"
    print(BANNER.format(
        env=ENV_FILE, env_state="已读取" if ENV else "未找到",
        base=JEV_BASE, model=JEV_MODEL,
        key=mask(JEV_KEY) or "未配置（手工模式仍可玩，AI 功能需填 .env）",
        host=args.host, port=args.port,
    ).replace("Jev 演示中心", f"Jev 演示中心 · {mode}"), flush=True)

    if getattr(sys, "frozen", False):
        print(f"  程序目录     : {runtime_root()}", flush=True)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
