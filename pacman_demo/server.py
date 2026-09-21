"""吃豆人 AI 决策对比 demo —— 本地服务（静态页面 + Jev / LLM 代理）

为什么必须要有这个代理？
    Jev API 的 CORS 白名单不接受任何 localhost 来源，浏览器直连会在预检阶段被拦掉：
        OPTIONS /v1/systemone  ->  400 Disallowed CORS origin
    所以页面不能直接 fetch api.typesafe.ai，必须由本地服务代为转发。
    代理还有个好处：base url / key 可以在页面上随时改，不用重启服务。

跑法：
    .venv/bin/python pacman_demo/server.py          # 用 .env 里的 key
    python3 pacman_demo/server.py                   # 纯标准库，系统 python3 也能跑
    python3 pacman_demo/server.py --port 9000

然后浏览器打开 http://127.0.0.1:8791
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = HERE / "index.html"
ZH_ASSETS = HERE.parent / "zh"      # 简繁切换器，和门户页共用同一份
ENV_FILE = HERE.parent / ".env"

DEFAULT_JEV_BASE = "https://api.typesafe.ai"
DEFAULT_LLM_BASE = "https://api.openai.com/v1"
DEFAULT_JEV_MODEL = "jev-latest"
DEFAULT_LLM_MODEL = "gpt-4o-mini"

UPSTREAM_TIMEOUT = 60.0


# --------------------------------------------------------------------------
# SSL：macOS 上系统 python3 经常找不到根证书，导致 CERTIFICATE_VERIFY_FAILED。
# 优先用 truststore（走 Keychain，和 venv 里 SDK 的行为一致），
# 退而求其次用 certifi，最后退回系统证书包。
# --------------------------------------------------------------------------
def build_ssl_context() -> ssl.SSLContext | None:
    try:
        import truststore  # type: ignore[import-not-found]

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        pass

    try:
        import certifi  # type: ignore[import-not-found]

        ctx = ssl.create_default_context(cafile=certifi.where())
        print(f"  SSL                : certifi ({certifi.where()})")
        return ctx
    except ImportError:
        pass

    for bundle in ("/etc/ssl/cert.pem", "/usr/local/etc/openssl/cert.pem"):
        if Path(bundle).exists():
            ctx = ssl.create_default_context(cafile=bundle)
            print(f"  SSL                : {bundle}")
            return ctx

    print("  SSL                : 未找到根证书包，将使用 python 默认设置")
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


def mask(key: str) -> str:
    """只回显 key 的尾巴，避免把完整密钥发给前端。"""
    if not key:
        return ""
    return f"{key[:12]}…{key[-4:]}" if len(key) > 20 else "已配置"


# --------------------------------------------------------------------------
# 上游调用
# --------------------------------------------------------------------------
def call_upstream(url: str, api_key: str, payload: dict, method: str = "POST") -> dict:
    """转发一次请求。永远返回 dict，不抛异常，让前端能拿到可读的错误。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    # 故意不带 Origin —— 服务端到服务端调用不触发 CORS

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
        detail = exc.read().decode("utf-8", "replace")[:2000]
        try:
            detail = json.loads(detail)
        except json.JSONDecodeError:
            pass
        return {"ok": False, "status": exc.code, "latencyMs": round(latency, 1), "error": detail}

    except urllib.error.URLError as exc:
        latency = (time.perf_counter() - started) * 1000
        return {"ok": False, "status": 0, "latencyMs": round(latency, 1), "error": f"连接失败: {exc.reason}"}

    except Exception as exc:  # noqa: BLE001 - 兜底，调试阶段要看到真实原因
        latency = (time.perf_counter() - started) * 1000
        return {"ok": False, "status": 0, "latencyMs": round(latency, 1), "error": f"{type(exc).__name__}: {exc}"}


def normalize_base(url: str, fallback: str) -> str:
    base = (url or "").strip().rstrip("/") or fallback
    if not re.match(r"^https?://", base):
        raise ValueError("base url 必须以 http:// 或 https:// 开头")
    return base


# --------------------------------------------------------------------------
# 三个接口的处理
# --------------------------------------------------------------------------
def resolve_key(provided: str, env_names: tuple[str, ...]) -> str:
    """前端没填 key 时，回落到 .env。这样 .env 配好了就能开箱即用。"""
    if provided and provided.strip():
        return provided.strip()
    for name in env_names:
        value = ENV.get(name, "").strip()
        if value:
            return value
    return ""


def handle_jev(body: dict) -> dict:
    """转发到 Jev 的 /v1/systemone"""
    base = normalize_base(body.get("baseUrl", ""), DEFAULT_JEV_BASE)
    payload = {
        "state": body.get("state"),
        "model": body.get("model") or DEFAULT_JEV_MODEL,
        "questions": body.get("questions"),
    }
    key = resolve_key(body.get("apiKey", ""), ("TYPESAFE_API_KEY",))
    return call_upstream(f"{base}/v1/systemone", key, payload)


def handle_llm(body: dict) -> dict:
    """转发到 OpenAI 兼容的 /chat/completions"""
    base = normalize_base(body.get("baseUrl", ""), DEFAULT_LLM_BASE)
    payload = {
        "model": body.get("model") or DEFAULT_LLM_MODEL,
        "messages": body.get("messages") or [],
        "temperature": body.get("temperature", 0),
        "max_tokens": body.get("maxTokens", 16),
    }
    if body.get("jsonMode", True):
        payload["response_format"] = {"type": "json_object"}
    key = resolve_key(body.get("apiKey", ""), ("LLM_API_KEY", "OPENAI_API_KEY"))
    return call_upstream(f"{base}/chat/completions", key, payload)


def handle_models(body: dict) -> dict:
    """列出可用模型。Jev 在 /v1/models，OpenAI 兼容在 /models。"""
    provider = body.get("provider", "jev")
    if provider == "jev":
        base = normalize_base(body.get("baseUrl", ""), DEFAULT_JEV_BASE)
        key = resolve_key(body.get("apiKey", ""), ("TYPESAFE_API_KEY",))
        return call_upstream(f"{base}/v1/models", key, None, method="GET")
    base = normalize_base(body.get("baseUrl", ""), DEFAULT_LLM_BASE)
    key = resolve_key(body.get("apiKey", ""), ("LLM_API_KEY", "OPENAI_API_KEY"))
    return call_upstream(f"{base}/models", key, None, method="GET")


def handle_config() -> dict:
    """给前端预填的默认值。key 只回显掩码，真正的 key 留在服务端。"""
    return {
        "ok": True,
        "status": 200,
        "data": {
            "jev": {
                "baseUrl": ENV.get("TYPESAFE_BASE_URL", "").strip() or DEFAULT_JEV_BASE,
                "model": ENV.get("TYPESAFE_DEFAULT_MODEL", "").strip() or DEFAULT_JEV_MODEL,
                "hasKey": bool(ENV.get("TYPESAFE_API_KEY")),
                "keyHint": mask(ENV.get("TYPESAFE_API_KEY", "")),
            },
            "llm": {
                "baseUrl": ENV.get("LLM_BASE_URL", "").strip() or DEFAULT_LLM_BASE,
                "model": ENV.get("LLM_MODEL", "").strip() or DEFAULT_LLM_MODEL,
                "hasKey": bool(ENV.get("LLM_API_KEY") or ENV.get("OPENAI_API_KEY")),
                "keyHint": mask(ENV.get("LLM_API_KEY") or ENV.get("OPENAI_API_KEY") or ""),
            },
        },
    }


MIME = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}

ROUTES = {
    "/api/jev": handle_jev,
    "/api/llm": handle_llm,
    "/api/models": handle_models,
}


# --------------------------------------------------------------------------
# HTTP handler
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "PacmanDemo/1.0"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A002
        # 只打印一行简版日志，别把 body 打出来（里面可能带 key）
        print(f"  {self.address_string()} {fmt % args}")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _serve_index(self) -> None:
        if not INDEX.exists():
            self.send_error(404, "index.html not found")
            return
        raw = INDEX.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _serve_zh(self, rel: str) -> None:
        """简繁切换器的静态文件（/zh/*）。

        单跑本服务时页面在根目录，门户页里则挂在 /pacman/ 下 —— 两种情况下
        页面都用 `../zh/zh.js` 引用，都会落到这里的 /zh/*。
        """
        target = (ZH_ASSETS / rel).resolve()
        # 挡住 ../ 穿越：解析后必须仍在 zh/ 目录里
        if not target.is_relative_to(ZH_ASSETS.resolve()) or not target.is_file():
            self.send_error(404)
            return
        raw = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._serve_index()
        elif self.path.startswith("/zh/"):
            self._serve_zh(self.path[len("/zh/"):].split("?", 1)[0])
        elif self.path == "/api/config":
            self._send_json(handle_config())
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_json()
        handler = ROUTES.get(self.path)
        if handler is None:
            self._send_json({"ok": False, "error": "unknown route"}, 404)
            return
        try:
            result = handler(body)
        except ValueError as exc:
            result = {"ok": False, "status": 400, "error": str(exc)}
        # 上游错误也用 200 返回，前端统一读 result.ok / result.error
        self._send_json(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="吃豆人 AI 对比 demo 本地服务")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    env_state = "已读取" if ENV else "未找到"
    print("=" * 78)
    print("  吃豆人 AI 决策对比 demo")
    print("=" * 78)
    print(f"  .env               : {ENV_FILE}  ({env_state})")
    print(f"  Jev base url       : {ENV.get('TYPESAFE_BASE_URL') or DEFAULT_JEV_BASE}")
    print(f"  Jev model          : {ENV.get('TYPESAFE_DEFAULT_MODEL') or DEFAULT_JEV_MODEL}")
    print(f"  Jev key            : {mask(ENV.get('TYPESAFE_API_KEY', '')) or '未配置（可在页面上填）'}")
    print(f"  LLM key            : {mask(ENV.get('LLM_API_KEY') or ENV.get('OPENAI_API_KEY') or '') or '未配置（请在页面上填）'}")
    print("-" * 78)
    print(f"  打开：http://{args.host}:{args.port}")
    print("  注意：一定从这个地址进。直接双击 index.html（file://）")
    print("        或换别的端口打开，页面都调不到 /api/*，会一直报 Failed to fetch。")
    print("  Ctrl-C 退出")
    print("=" * 78)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已退出")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
