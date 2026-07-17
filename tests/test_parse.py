"""파싱 순수 함수 테스트 — 핵심은 프로젝트명 추출(모든 사용자에게 동작)."""

from __future__ import annotations

import json

from recall.parse import Message, parse_line, project_name


def _line(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False)


# ── parse_line ──────────────────────────────────────────────────────────

def test_문자열_content():
    m = parse_line(_line(type="user", timestamp="2026-07-01T10:00:00Z",
                         message={"role": "user", "content": "테스트를 고쳐줘"}))
    assert m == Message("user", "2026-07-01T10:00:00Z", "테스트를 고쳐줘", None)


def test_블록_배열_content():
    m = parse_line(_line(type="assistant",
                         message={"content": [{"type": "text", "text": "고치는 중입니다"}]}))
    assert m.text == "고치는 중입니다"


def test_도구_호출도_색인한다():
    m = parse_line(_line(message={"content": [
        {"type": "text", "text": "명령 실행"},
        {"type": "tool_use", "name": "Bash"},
    ]}))
    assert "명령 실행" in m.text and "[tool:Bash]" in m.text


def test_짧은_텍스트는_버린다():
    assert parse_line(_line(message={"content": "ok"})) is None


def test_cwd만_있고_텍스트_없으면_cwd_때문에_살린다():
    m = parse_line(_line(cwd="/work/repo", message={"content": "ok"}))
    assert m is not None and m.cwd == "/work/repo" and m.text == ""


def test_비json_빈줄_잘린줄은_건너뛴다():
    assert parse_line("") is None
    assert parse_line("이건 json 이 아님") is None
    assert parse_line('{"불완전') is None
    assert parse_line("[1,2,3]") is None  # dict 아님


def test_긴_텍스트는_잘린다():
    m = parse_line(_line(message={"content": "가" * 9000}))
    assert len(m.text) == 4000


# ── project_name (핵심: 하드코딩 없이 아무 홈에서나 동작) ──────────────────

def test_cwd_의_마지막_조각을_쓴다():
    # 원본 코드는 '/Users/dawith' 를 하드코딩했다. cwd 기반은 누구에게나 맞는다.
    assert project_name("/home/alice/projects/my-api", "-home-alice-projects-my-api") == "my-api"
    assert project_name("/Users/bob/work/dashboard", "무엇이든") == "dashboard"


def test_cwd_끝의_슬래시를_무시한다():
    assert project_name("/work/repo/", "x") == "repo"


def test_루트_cwd():
    assert project_name("/", "-") == "/"


def test_cwd_없으면_폴더이름에서_최선():
    # 폴더 인코딩은 되돌릴 수 없다: '-home-alice-my-api' 는 경로 구분자('/')와
    # 낱말 속 하이픈('my-api')을 똑같이 '-' 로 만들어 어디가 경계인지 알 수 없다.
    # 그래서 마지막 조각('api')이 최선이다 — 완벽하진 않지만 라벨로는 동작한다.
    # 실제로는 cwd 가 거의 항상 기록에 있어 이 폴백은 드물게만 쓰인다.
    assert project_name(None, "-home-alice-my-api") == "api"
    assert project_name("", "-a---b-project") == "project"


def test_한글_경로는_인코딩에서_사라지지만_cwd로_복구된다():
    # 폴더명 '-Users-dawith---' 로는 '개발' 을 복구할 수 없다.
    # 하지만 기록 안의 cwd 로는 정확히 얻는다.
    assert project_name("/Users/dawith/개발", "-Users-dawith---") == "개발"
