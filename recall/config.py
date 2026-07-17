"""경로 설정 — XDG 규칙. 홈 경로를 코드에 박지 않는다."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Config"]


def _default_projects() -> Path:
    return Path.home() / ".claude" / "projects"


def _default_db() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "recall" / "index.db"


@dataclass(frozen=True)
class Config:
    #: Claude Code 가 세션 기록(jsonl)을 쌓는 곳
    projects_dir: Path = field(default_factory=_default_projects)
    #: 검색 인덱스를 둘 곳. /tmp 를 쓰지 않는다 (재부팅 시 사라짐)
    db_path: Path = field(default_factory=_default_db)

    @classmethod
    def from_env(cls) -> "Config":
        kw: dict[str, Path] = {}
        if p := os.environ.get("RECALL_PROJECTS_DIR"):
            kw["projects_dir"] = Path(p).expanduser()
        if p := os.environ.get("RECALL_DB"):
            kw["db_path"] = Path(p).expanduser()
        return cls(**kw)
