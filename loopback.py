#!/usr/bin/env python3
"""Loopback ChatGPT OAuth adapter for Grok luna children.

  python3 loopback.py --check
  python3 loopback.py --self-test
  python3 loopback.py --daemon   # detach HTTP singleton
  python3 loopback.py --stop     # kill our listener only
  grok plugin install . --trust  # MCP is .mcp.json + bin/run-mcp

:8743 is a host singleton. MCP stdio is per session. Do not talk to api.openai.com.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import IO


DEFAULT_PORT = 8743
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TOKEN_URL = "https://auth.openai.com/oauth/token"
UPSTREAM = "https://chatgpt.com/backend-api/codex/responses"
JWT_AUTH = "https://api.openai.com/auth"
ORIGINATOR = "codex_cli_rs"
REFUSE = (
    "codex_loopback: ChatGPT OAuth required. Run `codex login` and choose "
    "ChatGPT. auth_mode=apikey is not OAuth."
)


def die(msg: str, code: int = 1) -> None:
    print(f"codex-loopback: {msg}", file=sys.stderr)
    raise SystemExit(code)


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    dest = base / "sysop" / "codex-loopback"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def pidfile_path() -> Path:
    return cache_dir() / "server.pid"


def holders_path() -> Path:
    return cache_dir() / "holders.json"


def state_lock_path() -> Path:
    return cache_dir() / "state.lock"


def auth_lock_path() -> Path:
    return cache_dir() / "auth.lock"


def default_port() -> int:
    raw = os.environ.get("GROK_CODEX_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw)
    except ValueError:
        die(f"GROK_CODEX_PORT must be an int, got {raw!r}")
    if not 1 <= port <= 65535:
        die(f"port out of range: {port}")
    return port


def auth_path() -> Path:
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return home / "auth.json"


def load_auth() -> dict:
    path = auth_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def chatgpt_tokens(data: dict) -> tuple[str, str] | None:
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return None
    access = tokens.get("access_token")
    refresh = tokens.get("refresh_token")
    if isinstance(access, str) and access and isinstance(refresh, str) and refresh:
        return access, refresh
    return None


def auth_state(data: dict) -> str:
    mode = str(data.get("auth_mode") or "").lower()
    if mode == "apikey" or chatgpt_tokens(data) is None:
        return "refused"
    return "chatgpt"


def decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    raw = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        import base64

        payload = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")))
    except (ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def account_id(access: str, stored: dict) -> str:
    tokens = stored.get("tokens")
    if isinstance(tokens, dict):
        for key in ("account_id", "chatgpt_account_id"):
            value = tokens.get(key)
            if isinstance(value, str) and value:
                return value
    claims = decode_jwt_payload(access)
    auth = claims.get(JWT_AUTH)
    if isinstance(auth, dict):
        for key in ("chatgpt_account_id", "account_id"):
            value = auth.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def refresh_tokens(refresh: str) -> tuple[str, str]:
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": CLIENT_ID,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        die(f"token refresh failed: {exc}")
    access = payload.get("access_token")
    new_refresh = payload.get("refresh_token") or refresh
    if not isinstance(access, str) or not access:
        die("token refresh missing access_token")
    return access, new_refresh if isinstance(new_refresh, str) else refresh


def write_tokens(data: dict, access: str, refresh: str) -> None:
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}
    tokens["access_token"] = access
    tokens["refresh_token"] = refresh
    data["tokens"] = tokens
    data["auth_mode"] = "chatgpt"
    path = auth_path()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def locked_refresh(data: dict, refresh: str) -> tuple[str, dict]:
    """Serialize token refresh so two sessions do not clobber auth.json."""
    with open(auth_lock_path(), "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        current = load_auth()
        pair = chatgpt_tokens(current)
        if pair is None:
            pair = chatgpt_tokens(data)
        if pair is None:
            return "", data
        _access, current_refresh = pair
        access, new_refresh = refresh_tokens(current_refresh or refresh)
        write_tokens(current or data, access, new_refresh)
        return access, current or data


def strip_ids(item: object) -> object:
    if isinstance(item, dict):
        return {k: strip_ids(v) for k, v in item.items() if k != "id"}
    if isinstance(item, list):
        return [strip_ids(v) for v in item]
    return item


def rewrite_roles(item: object) -> object:
    """Codex ChatGPT rejects role=system. Grok sends those. Use developer."""
    if isinstance(item, dict):
        out = {k: rewrite_roles(v) for k, v in item.items()}
        if out.get("role") == "system":
            out["role"] = "developer"
        return out
    if isinstance(item, list):
        return [rewrite_roles(v) for v in item]
    return item


TERMINAL_TYPES = frozenset(
    {"response.completed", "response.incomplete", "response.failed"}
)


class OutputCollector:
    """Codex store:false leaves response.completed.output empty (HUB-171)."""

    def __init__(self) -> None:
        self._items: dict[int, dict] = {}

    def observe(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        if payload.get("type") != "response.output_item.done":
            return
        item = payload.get("item")
        idx = payload.get("output_index")
        if isinstance(item, dict) and isinstance(idx, int):
            self._items[idx] = item

    def fill(self, payload: object) -> object:
        if not isinstance(payload, dict):
            return payload
        if payload.get("type") not in TERMINAL_TYPES:
            return payload
        resp = payload.get("response")
        if not isinstance(resp, dict):
            return payload
        existing = resp.get("output")
        if isinstance(existing, list) and existing:
            return payload
        if not self._items:
            return payload
        out = dict(payload)
        new_resp = dict(resp)
        new_resp["output"] = [self._items[i] for i in sorted(self._items)]
        out["response"] = new_resp
        return out


def split_sse_blocks(buf: bytes) -> tuple[list[bytes], bytes]:
    blocks: list[bytes] = []
    while True:
        crlf = buf.find(b"\r\n\r\n")
        lf = buf.find(b"\n\n")
        if crlf < 0 and lf < 0:
            return blocks, buf
        if crlf >= 0 and (lf < 0 or crlf <= lf):
            raw, buf = buf[:crlf], buf[crlf + 4 :]
        else:
            raw, buf = buf[:lf], buf[lf + 2 :]
        if raw.strip():
            blocks.append(raw)
    return blocks, buf


def parse_sse(raw: bytes) -> tuple[str | None, str]:
    event = None
    data_lines: list[str] = []
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    return event, "\n".join(data_lines)


def format_sse(event: str | None, data: str) -> bytes:
    parts: list[str] = []
    if event:
        parts.append(f"event: {event}")
    parts.append(f"data: {data}")
    return ("\n".join(parts) + "\n\n").encode("utf-8")


def rewrite_sse_block(raw: bytes, collector: OutputCollector) -> bytes:
    event, data = parse_sse(raw)
    if not data or data == "[DONE]":
        return format_sse(event, data) if (event or data) else raw + b"\n\n"
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return raw + b"\n\n"
    collector.observe(payload)
    payload = collector.fill(payload)
    typ = payload.get("type") if isinstance(payload, dict) else None
    ev = event or (typ if isinstance(typ, str) else None)
    return format_sse(ev, json.dumps(payload, separators=(",", ":"), ensure_ascii=False))


EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})


def normalize_effort(raw: object) -> str:
    """Honor Grok's requested effort. Default high if missing or unknown."""
    if isinstance(raw, str) and raw.lower() in EFFORTS:
        return raw.lower()
    return "high"


def requested_effort(body: dict) -> object:
    reasoning = body.get("reasoning")
    if isinstance(reasoning, dict) and "effort" in reasoning:
        return reasoning.get("effort")
    for key in ("reasoning_effort", "effort"):
        if key in body:
            return body.get(key)
    return None


def transform(body: dict) -> dict:
    out = dict(body)
    out["model"] = "gpt-5.6-luna"
    out["store"] = False
    out["stream"] = True
    out.pop("service_tier", None)
    out.pop("reasoning_effort", None)
    out.pop("effort", None)
    reasoning = out.get("reasoning")
    if not isinstance(reasoning, dict):
        reasoning = {}
    reasoning["effort"] = normalize_effort(requested_effort(body))
    reasoning["mode"] = "standard"
    # Responses API: summary surfaces thinking so the TUI can show it.
    reasoning["summary"] = "auto"
    out["reasoning"] = reasoning
    raw_input = out.get("input")
    if isinstance(raw_input, list):
        kept = [item for item in raw_input if not (isinstance(item, dict) and item.get("type") == "item_reference")]
        out["input"] = rewrite_roles(strip_ids(kept))
    include = out.get("include")
    if not isinstance(include, list):
        include = []
    if "reasoning.encrypted_content" not in include:
        include = [*include, "reasoning.encrypted_content"]
    out["include"] = include
    return out


def pid_command(pid: int) -> str:
    try:
        return subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def is_ours(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    cmd = pid_command(pid)
    return "codex_loopback.py" in cmd or "loopback.py --http" in cmd or "loopback.py --port" in cmd


def pids_on_port(port: int) -> list[int]:
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    found: list[int] = []
    for token in out.split():
        try:
            found.append(int(token))
        except ValueError:
            continue
    return found


def read_pidfile() -> int | None:
    path = pidfile_path()
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def write_pidfile() -> None:
    pidfile_path().write_text(f"{os.getpid()}\n", encoding="utf-8")


def clear_pidfile() -> None:
    current = read_pidfile()
    if current is not None and current != os.getpid() and pid_alive(current):
        return
    try:
        pidfile_path().unlink()
    except OSError:
        pass


def stop_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not pid_alive(pid):
            return
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


def reclaim_port(port: int) -> None:
    seen: list[int] = []
    previous = read_pidfile()
    if previous is not None:
        seen.append(previous)
    for pid in pids_on_port(port):
        if pid not in seen:
            seen.append(pid)
    foreign = [pid for pid in seen if pid_alive(pid) and pid != os.getpid() and not is_ours(pid)]
    if foreign:
        die(f"port {port} held by {', '.join(str(pid) for pid in foreign)}")
    for pid in seen:
        if is_ours(pid):
            print(f"replace: pid {pid}", file=sys.stderr)
            stop_pid(pid)
    leftover = [pid for pid in pids_on_port(port) if pid != os.getpid()]
    if leftover:
        die(f"port {port} still in use after replace")
    clear_pidfile()


def _empty_holders() -> dict:
    return {"holders": [], "http_pid": None}


def load_holders() -> dict:
    path = holders_path()
    if not path.is_file():
        return _empty_holders()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_holders()
    if not isinstance(data, dict):
        return _empty_holders()
    holders = data.get("holders")
    if not isinstance(holders, list):
        holders = []
    clean: list[int] = []
    for item in holders:
        try:
            clean.append(int(item))
        except (TypeError, ValueError):
            continue
    http_pid = data.get("http_pid")
    try:
        http_pid_i = int(http_pid) if http_pid is not None else None
    except (TypeError, ValueError):
        http_pid_i = None
    return {"holders": clean, "http_pid": http_pid_i}


def save_holders(state: dict) -> None:
    holders_path().write_text(json.dumps(state) + "\n", encoding="utf-8")


def prune_holders(state: dict) -> dict:
    live = [pid for pid in state.get("holders", []) if isinstance(pid, int) and pid_alive(pid)]
    http_pid = state.get("http_pid")
    if isinstance(http_pid, int) and not pid_alive(http_pid):
        http_pid = None
    return {"holders": live, "http_pid": http_pid}


def with_state_lock(fn):  # type: ignore[no-untyped-def]
    def wrapped(*args, **kwargs):  # type: ignore[no-untyped-def]
        with open(state_lock_path(), "a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            return fn(*args, **kwargs)

    return wrapped


@with_state_lock
def add_holder(pid: int) -> dict:
    state = prune_holders(load_holders())
    if pid not in state["holders"]:
        state["holders"].append(pid)
    save_holders(state)
    return state


@with_state_lock
def drop_holder(pid: int) -> dict:
    state = prune_holders(load_holders())
    state["holders"] = [item for item in state["holders"] if item != pid]
    save_holders(state)
    return state


def http_ours(port: int) -> bool:
    listeners = pids_on_port(port)
    if not listeners:
        return False
    for pid in listeners:
        if pid != os.getpid() and not is_ours(pid):
            return False
    return True


def fetch_health(port: int) -> dict | None:
    url = f"http://127.0.0.1:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def http_healthy(port: int) -> bool:
    return http_ours(port) and fetch_health(port) is not None


def spawn_http_daemon(port: int) -> int:
    script = Path(__file__).resolve()
    log = open(cache_dir() / "http.log", "ab")
    proc = subprocess.Popen(
        [sys.executable, str(script), "--http", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
        close_fds=True,
    )
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if proc.poll() is not None:
            die(f"http daemon exited {proc.returncode}")
        if http_healthy(port):
            return proc.pid
        time.sleep(0.05)
    die("http daemon did not become healthy")
    return proc.pid


@with_state_lock
def ensure_http(port: int) -> dict:
    state = prune_holders(load_holders())
    if os.getpid() not in state["holders"]:
        state["holders"].append(os.getpid())
    if http_healthy(port):
        pid = read_pidfile()
        if pid is not None:
            state["http_pid"] = pid
        save_holders(state)
        return state
    listeners = pids_on_port(port)
    foreign = [pid for pid in listeners if pid != os.getpid() and not is_ours(pid)]
    if foreign:
        die(f"port {port} held by {', '.join(str(pid) for pid in foreign)}")
    if listeners and all(is_ours(pid) or pid == os.getpid() for pid in listeners):
        save_holders(state)
        return state
    http_pid = spawn_http_daemon(port)
    state["http_pid"] = http_pid
    save_holders(state)
    return state


@with_state_lock
def release_http(port: int, pid: int) -> dict:
    state = prune_holders(load_holders())
    state["holders"] = [item for item in state["holders"] if item != pid]
    save_holders(state)
    if state["holders"]:
        return state
    http_pid = state.get("http_pid") or read_pidfile()
    if isinstance(http_pid, int) and is_ours(http_pid):
        stop_pid(http_pid)
    leftover = [item for item in pids_on_port(port) if is_ours(item)]
    for item in leftover:
        stop_pid(item)
    if not pids_on_port(port):
        clear_pidfile()
        state["http_pid"] = None
        save_holders(state)
    return state


@with_state_lock
def replace_http(port: int) -> dict:
    state = prune_holders(load_holders())
    reclaim_port(port)
    http_pid = spawn_http_daemon(port)
    state["http_pid"] = http_pid
    save_holders(state)
    return state


def health_payload() -> dict:
    data = load_auth()
    state = prune_holders(load_holders())
    auth = auth_state(data)
    payload = {
        "ok": auth == "chatgpt",
        "auth": auth,
        "bind": f"127.0.0.1:{default_port()}",
        "holders": len(state["holders"]),
        "http_pid": state.get("http_pid") or read_pidfile(),
    }
    if auth != "chatgpt":
        payload["login"] = (
            "ChatGPT OAuth is not initialized. In a local terminal run: "
            "codex login  (choose ChatGPT, not an API key)."
        )
    return payload


def run_check() -> int:
    payload = health_payload()
    print(json.dumps(payload))
    if payload["auth"] == "refused":
        print(REFUSE, file=sys.stderr)
        return 1
    return 0


def proxy_responses(handler: BaseHTTPRequestHandler, raw: bytes) -> None:
    data = load_auth()
    if auth_state(data) != "chatgpt":
        body = json.dumps({"error": REFUSE}).encode("utf-8")
        handler.send_response(401)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return
    try:
        incoming = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        handler.send_error(400, "invalid json")
        return
    if not isinstance(incoming, dict):
        handler.send_error(400, "body must be an object")
        return
    pair = chatgpt_tokens(data)
    if pair is None:
        handler.send_error(401, REFUSE)
        return
    _access, refresh = pair
    access, data = locked_refresh(data, refresh)
    if not access:
        handler.send_error(401, REFUSE)
        return
    acct = account_id(access, data)
    transformed = json.dumps(transform(incoming)).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {access}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "responses=experimental",
        "originator": ORIGINATOR,
    }
    if acct:
        headers["chatgpt-account-id"] = acct
    req = urllib.request.Request(UPSTREAM, data=transformed, method="POST", headers=headers)
    try:
        upstream = urllib.request.urlopen(req, timeout=300)
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        handler.send_response(exc.code)
        handler.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)
        return
    except urllib.error.URLError as exc:
        handler.send_error(502, f"upstream: {exc.reason}")
        return
    with upstream:
        handler.send_response(upstream.status)
        ctype = upstream.headers.get("Content-Type", "application/json")
        handler.send_header("Content-Type", ctype)
        handler.end_headers()
        collector = OutputCollector()
        buf = b""
        while True:
            chunk = upstream.read(8192)
            if not chunk:
                if buf.strip():
                    handler.wfile.write(rewrite_sse_block(buf, collector))
                    handler.wfile.flush()
                break
            buf += chunk
            blocks, buf = split_sse_blocks(buf)
            for raw in blocks:
                handler.wfile.write(rewrite_sse_block(raw, collector))
                handler.wfile.flush()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path != "/health":
            self.send_error(404)
            return
        body = json.dumps(health_payload()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path != "/v1/responses":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        proxy_responses(self, raw)


def serve(port: int, *, replace: bool = True) -> int:
    if replace:
        reclaim_port(port)
    elif http_healthy(port):
        return 0
    elif pids_on_port(port):
        foreign = [pid for pid in pids_on_port(port) if pid != os.getpid() and not is_ours(pid)]
        if foreign:
            die(f"port {port} held by {', '.join(str(pid) for pid in foreign)}")
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    write_pidfile()
    print(f"bind:   127.0.0.1:{port}", flush=True)
    print(f"health: http://127.0.0.1:{port}/health", flush=True)
    print(f"auth:   {health_payload()['auth']}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        clear_pidfile()
    return 0


MCP_PROTOCOL = "2024-11-05"
MCP_TOOLS = [
    {
        "name": "health",
        "description": "Loopback auth, bind, and holder count. Does not start or stop the listener.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "replace",
        "description": "Replace the singleton HTTP listener on 127.0.0.1:8743. Keep session holders.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _read_byte(raw: IO[bytes]) -> bytes:
    chunk = raw.read(1)
    return chunk if chunk else b""


def _read_line(raw: IO[bytes]) -> bytes | None:
    buf = b""
    while True:
        chunk = _read_byte(raw)
        if not chunk:
            return buf or None
        buf += chunk
        if buf.endswith(b"\n"):
            return buf


def mcp_read(raw: IO[bytes]) -> tuple[dict | None, str]:
    """Unbuffered. peek() deadlocks. Returns (payload, framing)."""
    first = _read_byte(raw)
    if not first:
        return None, "lsp"
    if first in (b"{", b"["):
        rest = _read_line(raw)
        blob = first + (rest or b"")
        try:
            payload = json.loads(blob.decode("utf-8"))
        except json.JSONDecodeError:
            return None, "ndjson"
        return (payload if isinstance(payload, dict) else None), "ndjson"
    header = first
    while not (header.endswith(b"\r\n\r\n") or header.endswith(b"\n\n")):
        chunk = _read_byte(raw)
        if not chunk:
            return None, "lsp"
        header += chunk
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
        chunk = raw.read(length - len(body))
        if not chunk:
            return None, "lsp"
        body += chunk
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None, "lsp"
    return (payload if isinstance(payload, dict) else None), "lsp"


def mcp_write(payload: dict, framing: str = "lsp") -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if framing == "ndjson":
        os.write(1, raw + b"\n")
        return
    os.write(1, f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)


def mcp_result(req_id: object, result: object) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def mcp_error(req_id: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def mcp_handle(message: dict, port: int) -> dict | None:
    method = message.get("method")
    req_id = message.get("id")
    if not isinstance(method, str):
        return None
    if method == "initialize":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        version = params.get("protocolVersion")
        if not isinstance(version, str) or not version:
            version = MCP_PROTOCOL
        return mcp_result(
            req_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "openai-loopback", "version": "0.4.0"},
            },
        )
    if method == "notifications/initialized" or method.startswith("notifications/"):
        return None
    if method == "ping":
        return mcp_result(req_id, {})
    if method == "tools/list":
        return mcp_result(req_id, {"tools": MCP_TOOLS})
    if method == "prompts/list":
        return mcp_result(req_id, {"prompts": []})
    if method == "resources/list":
        return mcp_result(req_id, {"resources": []})
    if method == "resources/templates/list":
        return mcp_result(req_id, {"resourceTemplates": []})
    if method == "logging/setLevel":
        return mcp_result(req_id, {})
    if method == "tools/call":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        name = params.get("name")
        try:
            if name == "health":
                text = json.dumps(health_payload())
            elif name == "replace":
                replace_http(port)
                text = json.dumps(health_payload())
            else:
                return mcp_error(req_id, -32601, f"unknown tool: {name}")
        except SystemExit as exc:
            return mcp_error(req_id, -32000, str(exc))
        return mcp_result(req_id, {"content": [{"type": "text", "text": text}]})
    if method in ("shutdown", "exit"):
        return mcp_result(req_id, {}) if req_id is not None else None
    if req_id is None:
        return None
    return mcp_error(req_id, -32601, f"unknown method: {method}")


def run_mcp(port: int) -> int:
    print(f"openai-loopback mcp start file={Path(__file__).resolve()}", file=sys.stderr, flush=True)
    # Handshake must not touch HTTP or the state lock. Grok's 30s clock
    # is initialize + initialized. Attach the singleton after that.
    sys.stdout.flush()
    sys.stdout = sys.stderr
    stdin = os.fdopen(0, "rb", buffering=0)
    attached = False
    framing = "lsp"

    def cleanup(_signum: int | None = None, _frame: object = None) -> None:
        if attached:
            release_http(port, os.getpid())
        if _signum is not None:
            raise SystemExit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    try:
        while True:
            message, framing = mcp_read(stdin)
            if message is None:
                print("openai-loopback mcp eof", file=sys.stderr, flush=True)
                break
            method = message.get("method")
            print(f"openai-loopback mcp {method} frame={framing}", file=sys.stderr, flush=True)
            reply = mcp_handle(message, port)
            if reply is not None:
                mcp_write(reply, framing)
                print(f"openai-loopback mcp sent {method}", file=sys.stderr, flush=True)
            if method == "notifications/initialized" and not attached:
                try:
                    with open(state_lock_path(), "a+", encoding="utf-8") as lock:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        state = prune_holders(load_holders())
                        if os.getpid() not in state["holders"]:
                            state["holders"].append(os.getpid())
                        save_holders(state)
                    attached = True
                    print("openai-loopback mcp holder", file=sys.stderr, flush=True)
                except (OSError, BlockingIOError) as exc:
                    print(f"openai-loopback mcp holder skip: {exc}", file=sys.stderr, flush=True)
            if method == "exit":
                break
    finally:
        if attached:
            release_http(port, os.getpid())
    return 0


def run_stop(port: int) -> int:
    """Kill our listener on port. Leave foreign processes alone."""
    pids = pids_on_port(port)
    if not pids:
        print(f"nothing on :{port}")
        return 0
    stopped = 0
    for pid in pids:
        if is_ours(pid):
            print(f"stop {pid}", file=sys.stderr)
            stop_pid(pid)
            stopped += 1
        else:
            print(f"leave {pid} ({pid_command(pid)})", file=sys.stderr)
    leftover = [pid for pid in pids_on_port(port) if is_ours(pid)]
    if leftover:
        die(f"port {port} still held by {', '.join(str(pid) for pid in leftover)}")
    if stopped:
        clear_pidfile()
    return 0


def run_daemon(port: int) -> int:
    if not http_healthy(port):
        with open(state_lock_path(), "a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if not http_healthy(port):
                spawn_http_daemon(port)
    print(json.dumps(health_payload()))
    return 0 if health_payload()["auth"] != "refused" else 1


def run_self_test() -> int:
    collector = OutputCollector()
    done = {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "pong"}],
        },
    }
    completed = {"type": "response.completed", "response": {"status": "completed", "output": []}}
    collector.observe(done)
    filled = collector.fill(completed)
    if not isinstance(filled, dict):
        die("self-test: fill returned non-dict")
    output = filled.get("response", {}).get("output")
    if not (isinstance(output, list) and output and output[0]["content"][0]["text"] == "pong"):
        die(f"self-test: expected filled output, got {output!r}")
    already = {"type": "response.completed", "response": {"output": [{"type": "message"}]}}
    left = OutputCollector().fill(already)
    if not isinstance(left, dict) or left["response"]["output"] != [{"type": "message"}]:
        die("self-test: must leave a non-empty output alone")
    raw = (
        b"event: response.completed\n"
        b'data: {"type":"response.completed","response":{"output":[]}}\n\n'
    )
    sse_collector = OutputCollector()
    sse_collector.observe(done)
    rewritten = rewrite_sse_block(raw.strip(), sse_collector)
    _, data = parse_sse(rewritten.rstrip() if rewritten.endswith(b"\n\n") else rewritten)
    parsed = json.loads(data)
    text = parsed["response"]["output"][0]["content"][0]["text"]
    if text != "pong":
        die(f"self-test: sse rewrite missed text, got {text!r}")

    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="codex-loopback-test-"))
    os.environ["XDG_CACHE_HOME"] = str(tmp)
    me = os.getpid()
    add_holder(me)
    state = load_holders()
    if me not in state["holders"]:
        die(f"self-test: holder missing, {state!r}")
    dropped = drop_holder(me)
    if dropped["holders"]:
        die(f"self-test: holder lingered, {dropped!r}")
    listed = mcp_handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, 8743)
    if not listed or "health" not in json.dumps(listed):
        die(f"self-test: tools/list missing health, {listed!r}")
    from io import BytesIO

    msg = {"jsonrpc": "2.0", "id": 7, "method": "ping"}
    raw = json.dumps(msg).encode()
    framed_in = BytesIO(f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
    got, frame = mcp_read(framed_in)
    if got != msg or frame != "lsp":
        die(f"self-test: content-length read {got!r} {frame}")
    nd = BytesIO(raw + b"\n")
    got_nd, frame_nd = mcp_read(nd)
    if got_nd != msg or frame_nd != "ndjson":
        die(f"self-test: ndjson read {got_nd!r} {frame_nd}")

    forced = transform({"input": [], "reasoning": {"effort": "low"}})
    if forced["model"] != "gpt-5.6-luna":
        die(f"self-test: transform must send gpt-5.6-luna, got {forced['model']!r}")
    if forced["reasoning"]["effort"] != "low":
        die(f"self-test: transform must keep effort=low, got {forced['reasoning']!r}")
    defaulted = transform({"input": []})
    if defaulted["reasoning"]["effort"] != "high":
        die(f"self-test: missing effort must default high, got {defaulted['reasoning']!r}")
    from_top = transform({"input": [], "reasoning_effort": "xhigh"})
    if from_top["reasoning"]["effort"] != "xhigh":
        die(f"self-test: top-level reasoning_effort ignored, got {from_top['reasoning']!r}")

    print("self-test: ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="print auth state; exit 1 if refused")
    parser.add_argument("--self-test", action="store_true", help="canned SSE/holder/MCP check; no network")
    parser.add_argument("--mcp", action="store_true", help="MCP stdio + ensure HTTP singleton (plugin)")
    parser.add_argument("--http", action="store_true", help="foreground HTTP only (spawned by --mcp/--daemon)")
    parser.add_argument("--daemon", action="store_true", help="detach HTTP singleton and exit")
    parser.add_argument("--stop", action="store_true", help="kill our HTTP listener only")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    if args.port is not None and not 1 <= args.port <= 65535:
        die(f"port out of range: {args.port}")
    if args.port is not None:
        os.environ["GROK_CODEX_PORT"] = str(args.port)
    port = args.port if args.port is not None else default_port()
    if args.check:
        return run_check()
    if args.self_test:
        return run_self_test()
    if args.mcp:
        return run_mcp(port)
    if args.http:
        return serve(port, replace=False)
    if args.daemon:
        return run_daemon(port)
    if args.stop:
        return run_stop(port)
    return serve(port, replace=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
