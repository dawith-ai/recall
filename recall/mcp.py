"""recall 을 MCP 서버로 노출한다 — 에이전트가 자기 과거 세션을 직접 검색한다.

의존성 0. MCP 는 stdio 위의 줄 단위(newline-delimited) JSON-RPC 2.0 이므로 표준
라이브러리만으로 구현한다 (SDK 를 쓰면 의존성이 생겨 이 프로젝트의 핵심이 깨진다).

Claude Code 에 등록:
    claude mcp add recall -- recall serve

그러면 에이전트가 `search_sessions` / `resume_session` 도구로 자기 이력을 조회한다.
"이거 전에 어떻게 했더라" 를 사람이 아니라 에이전트가 스스로 찾는다 — 소급형 기억.

프로토콜: https://modelcontextprotocol.io (2025-06-18 기준으로 구현, 클라이언트 버전 에코)
"""

from __future__ import annotations

import json
import sys
from typing import Any

from recall import __version__
from recall.config import Config
from recall.store import SearchHit, Store

__all__ = ["handle_message", "serve", "TOOLS"]

_DEFAULT_PROTOCOL = "2025-06-18"

# tools/list 로 광고할 도구 정의. inputSchema 는 JSON Schema.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_sessions",
        "description": (
            "Search your own past Claude Code sessions by full text. Use this to recall "
            "how a problem was solved before, what was decided, or where something lives — "
            "instead of guessing or redoing work. Returns matching snippets with the session "
            "id to resume."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words to search for."},
                "project": {"type": "string", "description": "Limit to projects matching this."},
                "limit": {"type": "integer", "description": "Max results (default 10)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "resume_session",
        "description": (
            "Find the past session that best matches a query and return the exact shell command "
            "to resume it, with its working directory. Use when you want to continue earlier work."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words describing the session."},
            },
            "required": ["query"],
        },
    },
]


def _format_hits(hits: list[SearchHit]) -> str:
    if not hits:
        return "No matching past sessions. (Has `recall index` been run?)"
    lines = [f"{len(hits)} past session(s):", ""]
    for h in hits:
        snip = " ".join(h.snippet.split())
        lines.append(f"[{h.ts[:10]}] {h.project} · {h.role}")
        lines.append(f"  {snip}")
        lines.append(f"  resume: claude --resume {h.session}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _tool_search(cfg: Config, args: dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "query is required."
    project = args.get("project") or None
    limit = int(args.get("limit") or 10)
    with Store(cfg.db_path) as store:
        return _format_hits(store.search(query, project, limit))


def _tool_resume(cfg: Config, args: dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "query is required."
    with Store(cfg.db_path) as store:
        hits = store.search(query, None, 1)
    if not hits:
        return f"No session matched '{query}'."
    h = hits[0]
    cmd = f"cd {h.cwd} && claude --resume {h.session}" if h.cwd else f"claude --resume {h.session}"
    return f"# {h.project} · {h.ts[:10]}\n{cmd}"


_HANDLERS = {"search_sessions": _tool_search, "resume_session": _tool_resume}


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle_message(msg: dict[str, Any], cfg: Config) -> dict[str, Any] | None:
    """JSON-RPC 메시지 하나를 처리해 응답을 만든다. 알림(id 없음)이면 None.

    순수 함수 — stdio 없이 테스트할 수 있다.
    """
    method = msg.get("method")
    msg_id = msg.get("id")

    # 알림은 응답하지 않는다 (notifications/initialized 등)
    if msg_id is None:
        return None

    if method == "initialize":
        client_version = (msg.get("params") or {}).get("protocolVersion")
        return _result(
            msg_id,
            {
                # 클라이언트가 요청한 버전을 에코해 호환성을 최대화한다
                "protocolVersion": client_version or _DEFAULT_PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "recall", "version": __version__},
                "instructions": "Search your own past Claude Code sessions. Zero tokens.",
            },
        )

    if method == "ping":
        return _result(msg_id, {})

    if method == "tools/list":
        return _result(msg_id, {"tools": TOOLS})

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        handler = _HANDLERS.get(name)
        if handler is None:
            return _error(msg_id, -32602, f"Unknown tool: {name}")
        try:
            text = handler(cfg, params.get("arguments") or {})
            return _result(msg_id, {"content": [{"type": "text", "text": text}], "isError": False})
        except Exception as e:  # 도구 오류는 프로토콜 오류가 아니라 결과의 isError 로 돌려준다
            return _result(
                msg_id,
                {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True},
            )

    return _error(msg_id, -32601, f"Method not found: {method}")


def serve(cfg: Config | None = None) -> int:
    """stdio 로 MCP 서버를 돈다. 로그는 stderr 로, 프로토콜은 stdout 으로만."""
    cfg = cfg or Config.from_env()
    print("recall MCP server ready (stdio)", file=sys.stderr, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue  # 깨진 프레임은 건너뛴다
        response = handle_message(msg, cfg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0
