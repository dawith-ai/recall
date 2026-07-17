"""MCP 서버 테스트 — JSON-RPC 핸들러를 순수 함수로 검증 (stdio 없이).

MCP 프로토콜(2025-06-18)의 메시지 형태를 회귀 방지로 고정한다.
"""

from __future__ import annotations

import json

import pytest

from recall.config import Config
from recall.mcp import TOOLS, handle_message


def _write_session(projects, dir_name, session, text, cwd):
    d = projects / dir_name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{session}.jsonl").write_text(
        json.dumps({"cwd": cwd, "timestamp": "2026-07-01T10:00:00Z",
                    "message": {"role": "user", "content": text}}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def cfg(tmp_path):
    from recall.index import build_index

    c = Config(projects_dir=tmp_path / "projects", db_path=tmp_path / "index.db")
    _write_session(c.projects_dir, "-home-alice-my-api", "s1",
                   "OAuth 토큰 갱신 버그를 이렇게 고쳤다", "/home/alice/my-api")
    build_index(c)
    return c


# ── 프로토콜 핸드셰이크 ──────────────────────────────────────────────────

def test_initialize_응답_형태(cfg):
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {}}},
        cfg,
    )
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    r = resp["result"]
    assert r["protocolVersion"] == "2025-06-18"      # 클라이언트 버전 에코
    assert "tools" in r["capabilities"]
    assert r["serverInfo"]["name"] == "recall"


def test_initialize_버전없으면_기본값(cfg):
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, cfg
    )
    assert resp["result"]["protocolVersion"]  # 비어있지 않은 기본 버전


def test_initialized_알림은_응답없음(cfg):
    # 알림은 id 가 없다 → None 반환 (stdout 에 아무것도 쓰지 않아야 함)
    assert handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, cfg) is None


def test_ping(cfg):
    resp = handle_message({"jsonrpc": "2.0", "id": 9, "method": "ping"}, cfg)
    assert resp["result"] == {}


# ── tools/list ───────────────────────────────────────────────────────────

def test_tools_list(cfg):
    resp = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, cfg)
    tools = resp["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == {"search_sessions", "resume_session"}
    for t in tools:
        assert t["inputSchema"]["type"] == "object"
        assert "query" in t["inputSchema"]["required"]


def test_tools_는_모듈상수와_일치(cfg):
    resp = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, cfg)
    assert resp["result"]["tools"] == TOOLS


# ── tools/call ───────────────────────────────────────────────────────────

def test_search_sessions_호출(cfg):
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "search_sessions", "arguments": {"query": "OAuth"}}},
        cfg,
    )
    r = resp["result"]
    assert r["isError"] is False
    text = r["content"][0]["text"]
    assert "my-api" in text
    assert "claude --resume s1" in text


def test_search_한국어(cfg):
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "search_sessions", "arguments": {"query": "토큰"}}},
        cfg,
    )
    assert "s1" in resp["result"]["content"][0]["text"]


def test_resume_session_호출(cfg):
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "resume_session", "arguments": {"query": "OAuth"}}},
        cfg,
    )
    text = resp["result"]["content"][0]["text"]
    assert "cd /home/alice/my-api && claude --resume s1" in text


def test_query_없으면_안내(cfg):
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "search_sessions", "arguments": {}}},
        cfg,
    )
    assert "required" in resp["result"]["content"][0]["text"]


def test_없는_도구는_에러(cfg):
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "delete_everything", "arguments": {}}},
        cfg,
    )
    assert resp["error"]["code"] == -32602


def test_없는_메서드는_에러(cfg):
    resp = handle_message({"jsonrpc": "2.0", "id": 6, "method": "nonsense"}, cfg)
    assert resp["error"]["code"] == -32601


def test_응답은_한_줄_json_으로_직렬화된다(cfg):
    """stdio 전송은 줄 단위 JSON 이다 — 응답에 내부 개행이 없어야 한다."""
    resp = handle_message(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "search_sessions", "arguments": {"query": "OAuth"}}},
        cfg,
    )
    line = json.dumps(resp)
    assert "\n" not in line
    assert json.loads(line)["id"] == 3  # 왕복
