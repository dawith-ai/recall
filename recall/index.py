"""세션 기록을 검색 인덱스로 만든다 — 증분(변경된 파일만)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from recall.config import Config
from recall.parse import parse_line, project_name
from recall.store import Store

__all__ = ["IndexResult", "build_index"]


@dataclass(frozen=True)
class IndexResult:
    new_files: int
    updated_files: int
    total_messages: int
    fts: bool


def _rows_for_file(jsonl: Path) -> list[tuple]:
    """한 세션 파일 → 색인 행들. 프로젝트명은 파일 안의 실제 cwd 에서 얻는다."""
    session = jsonl.stem
    dir_name = jsonl.parent.name
    messages = []
    cwd = ""
    try:
        with jsonl.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                msg = parse_line(line)
                if msg is None:
                    continue
                if msg.cwd and not cwd:
                    cwd = msg.cwd  # 세션 전체의 cwd (보통 첫 줄에 있다)
                if msg.text:
                    messages.append(msg)
    except OSError:
        return []

    project = project_name(cwd or None, dir_name)
    return [(project, session, cwd, m.role, m.ts, m.text) for m in messages]


def build_index(cfg: Config) -> IndexResult:
    """새/변경된 세션만 다시 색인한다. mtime 으로 판단하므로 반복 실행이 빠르다."""
    new = updated = 0
    with Store(cfg.db_path) as store:
        seen = store.indexed_mtimes()
        if cfg.projects_dir.exists():
            for jsonl in cfg.projects_dir.rglob("*.jsonl"):
                path = str(jsonl)
                try:
                    mtime = jsonl.stat().st_mtime
                except OSError:
                    continue
                if seen.get(path) == mtime:
                    continue
                if path in seen:
                    store.drop_session(jsonl.stem)
                    updated += 1
                else:
                    new += 1
                rows = _rows_for_file(jsonl)
                if rows:
                    store.add_messages(rows)
                store.mark_file(path, mtime)
        store.commit()
        _, total = store.counts()
        return IndexResult(new, updated, total, store.fts)
