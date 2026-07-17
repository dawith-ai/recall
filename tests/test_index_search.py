"""인덱싱·검색 통합 테스트 — 픽스처 세션 디렉터리로 끝에서 끝까지."""

from __future__ import annotations

import json
import os

import pytest

from recall.config import Config
from recall.index import build_index
from recall.store import Store


def _line(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False)


def _write_session(projects, dir_name, session, lines, mtime=None):
    d = projects / dir_name
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{session}.jsonl"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if mtime is not None:
        os.utime(f, (mtime, mtime))
    return f


@pytest.fixture
def cfg(tmp_path):
    return Config(projects_dir=tmp_path / "projects", db_path=tmp_path / "db" / "index.db")


def _seed(projects):
    _write_session(projects, "-home-alice-my-api", "s1", [
        _line(cwd="/home/alice/my-api", type="user",
              timestamp="2026-07-01T10:00:00Z",
              message={"role": "user", "content": "OAuth 토큰 갱신을 어떻게 고쳤더라"}),
        _line(type="assistant",
              message={"content": [{"type": "text", "text": "refresh_token 을 키체인에 저장했습니다"}]}),
    ])
    _write_session(projects, "-home-alice-docs", "s2", [
        _line(cwd="/home/alice/docs", type="user",
              message={"role": "user", "content": "sqlite FTS5 인덱스를 만들자"}),
    ])


def test_색인하고_검색한다(cfg):
    _seed(cfg.projects_dir)
    r = build_index(cfg)
    assert r.new_files == 2
    assert r.total_messages == 3

    with Store(cfg.db_path) as store:
        hits = store.search("OAuth", None, 10)
        assert len(hits) == 1
        assert hits[0].project == "my-api"       # cwd 에서 정확히
        assert hits[0].cwd == "/home/alice/my-api"
        assert hits[0].session == "s1"


def test_프로젝트로_한정한다(cfg):
    _seed(cfg.projects_dir)
    build_index(cfg)
    with Store(cfg.db_path) as store:
        assert len(store.search("인덱스", "docs", 10)) == 1
        assert len(store.search("인덱스", "my-api", 10)) == 0


def test_한국어_부분검색(cfg):
    """기본 FTS5 는 '인덱스' 로 '인덱스를' 을 못 찾는다(어절 토큰화). trigram 은 찾는다.
    한국어 사용자에게 검색이 조용히 실패하던 것을 막는 회귀 방지 테스트."""
    _seed(cfg.projects_dir)
    build_index(cfg)
    with Store(cfg.db_path) as store:
        assert len(store.search("인덱스", None, 10)) == 1   # '인덱스를' 안에서 찾음
        assert len(store.search("토큰 갱신", None, 10)) == 1  # 공백 포함 구절
        assert len(store.search("갱신을", None, 10)) == 1     # 조사 붙은 채로도


def test_증분_변경된_파일만_다시_색인(cfg):
    _seed(cfg.projects_dir)
    build_index(cfg)
    # 두 번째 실행은 변경이 없으므로 신규·갱신 0
    r2 = build_index(cfg)
    assert r2.new_files == 0 and r2.updated_files == 0
    assert r2.total_messages == 3


def test_세션_수정하면_갱신되고_중복되지_않는다(cfg):
    _seed(cfg.projects_dir)
    build_index(cfg)
    f = cfg.projects_dir / "-home-alice-docs" / "s2.jsonl"
    f.write_text(
        _line(cwd="/home/alice/docs", message={"content": "완전히 새로운 내용으로 교체"}) + "\n",
        encoding="utf-8",
    )
    os.utime(f, None)  # mtime 갱신
    r = build_index(cfg)
    assert r.updated_files == 1
    with Store(cfg.db_path) as store:
        assert len(store.search("FTS5", None, 10)) == 0        # 옛 내용 사라짐
        assert len(store.search("새로운", None, 10)) == 1       # 새 내용
        _, total = store.counts()
        assert total == 3  # s1(메시지 2) + s2(교체돼 1). 옛 s2 는 삭제됨 — 중복 없음


def test_projects_없어도_죽지_않는다(tmp_path):
    cfg = Config(projects_dir=tmp_path / "없음", db_path=tmp_path / "db.sqlite")
    r = build_index(cfg)
    assert r.total_messages == 0


def test_특수문자_질의도_터지지_않는다(cfg):
    """FTS5 MATCH 는 특수문자에 문법 오류를 낸다. 구 검색으로 안전하게 폴백해야 한다."""
    _write_session(cfg.projects_dir, "-x", "s", [
        _line(cwd="/x", message={"content": "함수 foo() 를 호출: a AND b OR c"}),
    ])
    build_index(cfg)
    with Store(cfg.db_path) as store:
        # 이 질의들은 순진하게 넣으면 FTS5 파서를 깨뜨린다
        for q in ["foo()", "a AND b", '"미완성', "c:d"]:
            store.search(q, None, 10)  # 예외 없이 반환되면 통과
