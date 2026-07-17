"""세션 기록(jsonl) 파싱 — 순수 함수, 표준 라이브러리만.

인덱싱·검색과 분리돼 있어 어디서든 테스트할 수 있다. I/O 없음.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

__all__ = ["Message", "parse_line", "project_name", "MIN_TEXT_LEN", "MAX_TEXT_LEN"]

#: 이보다 짧은 텍스트는 색인하지 않는다 ("ok", "네" 같은 잡음 제거)
MIN_TEXT_LEN = 8
#: 한 메시지에서 색인할 최대 길이. 거대한 붙여넣기가 인덱스를 부풀리지 않게 자른다
MAX_TEXT_LEN = 4000


@dataclass(frozen=True)
class Message:
    role: str
    ts: str
    text: str
    #: 이 줄에 cwd 가 있으면 담는다. 세션의 프로젝트를 정확히 알아내는 근거
    cwd: str | None = None


def _blocks_to_text(content: object) -> str:
    """Claude 의 content 필드(문자열 또는 블록 배열)를 평문으로."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text" and block.get("text"):
            parts.append(str(block["text"]))
        elif kind == "tool_use" and block.get("name"):
            # 도구 호출도 검색 대상이다 ("그때 어떤 명령 썼더라")
            parts.append(f"[tool:{block['name']}]")
    return " ".join(parts)


def parse_line(line: str) -> Message | None:
    """jsonl 한 줄 → Message. 대화 텍스트가 없거나 너무 짧으면 None.

    비-JSON, 빈 줄, 잘린 줄은 조용히 건너뛴다 — 실제 기록에는 흔하다.
    """
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None

    role = str(obj.get("type") or obj.get("role") or "")
    ts = str(obj.get("timestamp") or "")
    cwd = obj.get("cwd") if isinstance(obj.get("cwd"), str) and obj.get("cwd") else None

    msg = obj.get("message")
    content = msg.get("content") if isinstance(msg, dict) else obj.get("content")
    text = _blocks_to_text(content).strip()

    if len(text) < MIN_TEXT_LEN:
        # 텍스트가 없어도 cwd 만 있으면 프로젝트 판별에 쓰이므로 살려 보낸다
        return Message(role, ts, "", cwd) if cwd else None
    return Message(role, ts, text[:MAX_TEXT_LEN], cwd)


def project_name(cwd: str | None, dir_name: str) -> str:
    """세션이 속한 프로젝트의 사람이 읽을 이름.

    Claude Code 는 프로젝트 폴더를 cwd 의 모든 비영숫자 문자를 '-' 로 바꿔 만든다.
    이 인코딩은 되돌릴 수 없다(예: '/a/개발' → '-a---'). 그래서 폴더 이름을 디코딩하는
    대신, 기록 안에 저장된 실제 cwd 의 마지막 경로 조각을 쓴다 — 정확하고, 누구의
    홈 경로에도 의존하지 않는다. cwd 를 못 찾으면 폴더 이름에서 최선을 다한다.
    """
    if cwd:
        base = cwd.rstrip("/").rsplit("/", 1)[-1]
        if base:
            return base
        if cwd.strip("/") == "":
            return "/"  # 루트에서 실행된 세션
    # 폴백: 폴더 이름의 마지막 '-' 뒤 조각 (완벽하진 않지만 라벨로는 쓸 만하다)
    tail = dir_name.rstrip("-").rsplit("-", 1)[-1]
    return tail or dir_name or "unknown"
