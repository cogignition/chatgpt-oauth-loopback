#!/usr/bin/env python3
"""Grok stdio MCP for ChatGPT OAuth loopback. Does not bind :8743."""
from __future__ import annotations

import fcntl
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

LOGIN = (
    "ChatGPT OAuth is not initialized. In a local terminal run:\n"
    "  codex login\n"
    "Choose ChatGPT, not an API key. Then retry this server."
)


def log(msg: str) -> None:
    print(f"chatgpt-oauth {msg}", file=sys.stderr, flush=True)


def auth_path() -> Path:
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return home / "auth.json"


def local_auth() -> str:
    path = auth_path()
    if not path.is_file():
        return "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "missing"
    if not isinstance(data, dict):
        return "missing"
    if str(data.get("auth_mode") or "").lower() == "apikey":
        return "apikey"
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return "missing"
    access = tokens.get("access_token")
    refresh = tokens.get("refresh_token")
    if isinstance(access, str) and access and isinstance(refresh, str) and refresh:
        return "chatgpt"
    return "missing"


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    dest = base / "sysop" / "codex-loopback"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def holders_path() -> Path:
    return cache_dir() / "holders.json"


def state_lock_path() -> Path:
    return cache_dir() / "state.lock"


def pidfile_path() -> Path:
    return cache_dir() / "server.pid"


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def load_holders() -> dict:
    path = holders_path()
    if not path.is_file():
        return {"holders": [], "http_pid": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"holders": [], "http_pid": None}
    if not isinstance(data, dict):
        return {"holders": [], "http_pid": None}
    raw = data.get("holders")
    holders = []
    if isinstance(raw, list):
        for item in raw:
            try:
                holders.append(int(item))
            except (TypeError, ValueError):
                continue
    http_pid = data.get("http_pid")
    try:
        http_pid_i = int(http_pid) if http_pid is not None else None
    except (TypeError, ValueError):
        http_pid_i = None
    return {"holders": holders, "http_pid": http_pid_i}


def prune_holders(state: dict) -> dict:
    live = [pid for pid in state.get("holders", []) if pid_alive(pid)]
    http_pid = state.get("http_pid")
    if isinstance(http_pid, int) and not pid_alive(http_pid):
        http_pid = None
    return {"holders": live, "http_pid": http_pid}


def attach_holder() -> None:
    """After handshake. Last holder out kills :8743."""
    try:
        lock = open(state_lock_path(), "a+", encoding="utf-8")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError) as exc:
        log(f"holder skip {exc}")
        return
    try:
        state = prune_holders(load_holders())
        me = os.getpid()
        if me not in state["holders"]:
            state["holders"].append(me)
        holders_path().write_text(json.dumps(state) + "\n", encoding="utf-8")
        log(f"holder={me} n={len(state['holders'])}")
    finally:
        lock.close()


def release_holder() -> None:
    try:
        lock = open(state_lock_path(), "a+", encoding="utf-8")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    except OSError as exc:
        log(f"release skip {exc}")
        return
    try:
        state = prune_holders(load_holders())
        me = os.getpid()
        state["holders"] = [pid for pid in state["holders"] if pid != me]
        holders_path().write_text(json.dumps(state) + "\n", encoding="utf-8")
        log(f"holder drop n={len(state['holders'])}")
        if state["holders"]:
            return
        http_pid = state.get("http_pid")
        if http_pid is None:
            try:
                http_pid = int(pidfile_path().read_text().strip())
            except (OSError, ValueError):
                http_pid = None
        if isinstance(http_pid, int) and pid_alive(http_pid):
            log(f"lights out pid={http_pid}")
            try:
                os.kill(http_pid, signal.SIGTERM)
            except OSError:
                pass
            deadline = time.time() + 2.0
            while time.time() < deadline and pid_alive(http_pid):
                time.sleep(0.05)
            if pid_alive(http_pid):
                try:
                    os.kill(http_pid, signal.SIGKILL)
                except OSError:
                    pass
        state["http_pid"] = None
        holders_path().write_text(json.dumps(state) + "\n", encoding="utf-8")
        try:
            pidfile_path().unlink()
        except OSError:
            pass
    finally:
        lock.close()


def with_login(payload: dict) -> dict:
    auth = payload.get("auth") or local_auth()
    payload["auth"] = auth
    if auth != "chatgpt":
        payload["ok"] = False
        payload["login"] = LOGIN
    return payload


def read_byte() -> bytes:
    return os.read(0, 1)


def read_line() -> bytes:
    buf = b""
    while True:
        chunk = read_byte()
        if not chunk:
            return buf
        buf += chunk
        if buf.endswith(b"\n"):
            return buf


def read_msg() -> tuple[dict | None, str]:
    first = read_byte()
    if not first:
        return None, "ndjson"
    if first in (b"{", b"["):
        line = first + read_line()
        try:
            payload = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            return None, "ndjson"
        return (payload if isinstance(payload, dict) else None), "ndjson"
    header = first
    while not (header.endswith(b"\r\n\r\n") or header.endswith(b"\n\n")):
        chunk = read_byte()
        if not chunk:
            return None, "lsp"
        header += chunk
        if len(header) > 4096:
            return None, "lsp"
    headers: dict[str, str] = {}
    for line in header.decode("utf-8", "replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length") or "0")
    if length <= 0:
        return None, "lsp"
    body = b""
    while len(body) < length:
        chunk = os.read(0, length - len(body))
        if not chunk:
            return None, "lsp"
        body += chunk
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None, "lsp"
    return (payload if isinstance(payload, dict) else None), "lsp"


def write_msg(payload: dict, framing: str = "ndjson") -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if framing == "lsp":
        os.write(1, f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)
        return
    os.write(1, raw + b"\n")


def health() -> dict:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8743/health", timeout=2) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if not isinstance(payload, dict):
            payload = {"ok": False, "error": "bad health json"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        payload = {"ok": False, "error": str(exc), "bind": "127.0.0.1:8743"}
    return with_login(payload)


TOOLS = [
    {
        "name": "health",
        "description": "ChatGPT OAuth status and :8743 bind. If refused, tells you to run codex login.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "login",
        "description": "How to initialize ChatGPT OAuth locally. Does not run the login (MCP stdin is not a TTY).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "initialize":
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        version = params.get("protocolVersion")
        if not isinstance(version, str) or not version:
            version = "2024-11-05"
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "chatgpt-oauth", "version": "0.4.1"},
            },
        }
    if isinstance(method, str) and method.startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        name = params.get("name")
        if name == "health":
            text = json.dumps(health())
        elif name == "login":
            text = json.dumps(with_login({"auth": local_auth()}))
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"unknown tool: {name}"},
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": text}]},
        }
    if req_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"unknown method: {method}"},
    }


def main() -> int:
    sys.stdout = sys.stderr
    log(f"start plugin={os.path.abspath(__file__)}")
    auth = local_auth()
    if auth != "chatgpt":
        log(LOGIN.replace("\n", " | "))
    attached = False

    def cleanup(_signum: int | None = None, _frame: object = None) -> None:
        if attached:
            release_holder()
        if _signum is not None:
            raise SystemExit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    try:
        while True:
            msg, framing = read_msg()
            if msg is None:
                log("eof")
                break
            method = msg.get("method")
            log(f"recv {method} frame={framing}")
            reply = handle(msg)
            if reply is not None:
                write_msg(reply, framing)
                log(f"sent {method} frame={framing}")
            if method == "notifications/initialized" and not attached:
                attach_holder()
                attached = True
    finally:
        if attached:
            release_holder()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
