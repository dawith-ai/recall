"""CLI 종단 테스트 — index → search → resume 흐름."""

from __future__ import annotations

import json
import os

import pytest

from recall import cli


def _line(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False)


@pytest.fixture
def env(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    d = projects / "-home-alice-my-api"
    d.mkdir(parents=True)
    (d / "s1.jsonl").write_text(
        _line(type="user", cwd="/home/alice/my-api", timestamp="2026-07-01T10:00:00Z",
              message={"role": "user", "content": "OAuth 토큰 갱신 버그를 고쳤다"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RECALL_PROJECTS_DIR", str(projects))
    monkeypatch.setenv("RECALL_DB", str(tmp_path / "index.db"))
    return tmp_path


def test_index_then_search(env, capsys):
    assert cli.main(["index"]) == 0
    assert "색인 완료" in capsys.readouterr().out

    assert cli.main(["search", "OAuth"]) == 0
    out = capsys.readouterr().out
    assert "my-api" in out
    assert "claude --resume s1" in out


def test_search_없으면_안내(env, capsys):
    cli.main(["index"])
    capsys.readouterr()
    cli.main(["search", "존재하지않는질의어xyz"])
    assert "없습니다" in capsys.readouterr().out


def test_resume는_cd와_resume_명령을_출력(env, capsys):
    cli.main(["index"])
    capsys.readouterr()
    rc = cli.main(["resume", "OAuth"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "cd /home/alice/my-api && claude --resume s1" in out


def test_resume_맞는게_없으면_실패코드(env, capsys):
    cli.main(["index"])
    capsys.readouterr()
    assert cli.main(["resume", "절대없는질의어xyz"]) == 1


def test_stats(env, capsys):
    cli.main(["index"])
    capsys.readouterr()
    cli.main(["stats"])
    out = capsys.readouterr().out
    assert "인덱스:" in out and "my-api" in out
    assert "기간:" in out       # 날짜 범위
    assert "역할:" in out       # 역할 분포


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert "recall" in capsys.readouterr().out


def test_인자_없으면_도움말(capsys):
    assert cli.main([]) == 0
    assert "recall" in capsys.readouterr().out.lower()
