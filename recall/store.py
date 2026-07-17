"""SQLite 저장소 — 스키마, FTS5 감지, 증분 추적.

FTS5(전문 검색)를 우선 쓰고, 없는 빌드에서는 일반 테이블 + LIKE 로 자동 폴백한다.
그래서 어떤 파이썬/SQLite 조합에서도 동작한다.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Store", "SearchHit"]

#: 색인하는 컬럼. text 는 4번(0-based) — snippet() 에 그 인덱스를 넘긴다
_COLUMNS = "project, session, cwd, role, ts, text"
_TEXT_COL = 5


@dataclass(frozen=True)
class SearchHit:
    project: str
    session: str
    cwd: str
    role: str
    ts: str
    #: 검색어 주변 발췌 (FTS5 는 하이라이트, LIKE 는 앞부분)
    snippet: str


class Store:
    """세션 색인 데이터베이스. with 문으로 열고 닫는다."""

    def __init__(self, db_path: Path):
        self.path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.fts = self._init_schema()

    def _init_schema(self) -> bool:
        """검색 테이블을 만든다. trigram → 일반 FTS5 → LIKE 순으로 폴백.

        trigram 토크나이저를 우선하는 이유: 기본 FTS5(unicode61)는 한국어를 어절 단위로
        토큰화해서 '인덱스' 로 '인덱스를' 을 못 찾는다(한 토큰으로 붙음). 한국어 사용자에게는
        검색이 조용히 실패하는 셈이다. trigram 은 부분 문자열로 매칭해 한국어와 코드 심볼
        (foo() 등)을 모두 찾는다 — 'grep my sessions' 라는 이 도구의 목적에 정확히 맞는다.
        (trigram 은 SQLite 3.34+ 필요.)
        """
        c = self.conn
        c.execute("CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, mtime REAL)")

        existing = c.execute("PRAGMA user_version").fetchone()[0]
        if c.execute("SELECT name FROM sqlite_master WHERE name='msgs'").fetchone():
            return existing >= 1  # 이미 만들어진 인덱스의 엔진을 그대로 쓴다

        for ddl, version in (
            (f"CREATE VIRTUAL TABLE msgs USING fts5({_COLUMNS}, tokenize='trigram')", 2),
            (f"CREATE VIRTUAL TABLE msgs USING fts5({_COLUMNS})", 1),
            (f"CREATE TABLE msgs({_COLUMNS})", 0),
        ):
            try:
                c.execute(ddl)
                c.execute(f"PRAGMA user_version={version}")
                return version >= 1
            except sqlite3.OperationalError:
                continue
        return False

    # ── 증분 인덱싱 ──────────────────────────────────────────────────────

    def indexed_mtimes(self) -> dict[str, float]:
        return dict(self.conn.execute("SELECT path, mtime FROM files").fetchall())

    def drop_session(self, session: str) -> None:
        self.conn.execute("DELETE FROM msgs WHERE session=?", (session,))

    def add_messages(self, rows: list[tuple]) -> None:
        self.conn.executemany(
            f"INSERT INTO msgs({_COLUMNS}) VALUES(?,?,?,?,?,?)", rows
        )

    def mark_file(self, path: str, mtime: float) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO files(path, mtime) VALUES(?,?)", (path, mtime)
        )

    def commit(self) -> None:
        self.conn.commit()

    # ── 조회 ────────────────────────────────────────────────────────────

    def counts(self) -> tuple[int, int]:
        files = self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        msgs = self.conn.execute("SELECT COUNT(*) FROM msgs").fetchone()[0]
        return files, msgs

    def by_project(self, limit: int = 10) -> list[tuple[str, int]]:
        return self.conn.execute(
            "SELECT project, COUNT(*) n FROM msgs GROUP BY project ORDER BY n DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def date_range(self) -> tuple[str | None, str | None]:
        """색인된 메시지의 가장 이른/늦은 타임스탬프. 빈 문자열은 제외한다."""
        row = self.conn.execute(
            "SELECT MIN(ts), MAX(ts) FROM msgs WHERE ts != ''"
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)

    def role_counts(self) -> list[tuple[str, int]]:
        return self.conn.execute(
            "SELECT role, COUNT(*) n FROM msgs WHERE role != '' "
            "GROUP BY role ORDER BY n DESC"
        ).fetchall()

    #: trigram 토크나이저가 트라이그램을 만들려면 최소 3글자가 필요하다.
    #: 그보다 짧은 질의(한국어 2글자 '토큰'·'버그' 등)는 LIKE 부분검색으로 우회한다.
    _MIN_FTS_LEN = 3

    def search(self, query: str, project: str | None, limit: int) -> list[SearchHit]:
        if self.fts and len(query.strip()) >= self._MIN_FTS_LEN:
            rows = self._search_fts(query, project, limit)
        else:
            rows = self._search_like(query, project, limit)
        return [SearchHit(*r) for r in rows]

    def _search_fts(self, query: str, project: str | None, limit: int) -> list[tuple]:
        # 질의를 구(phrase)로 감싼다: 사용자가 넣은 특수문자(foo(), a AND b, ":" 등)가
        # FTS5 문법으로 해석돼 터지는 것을 막고, 입력 그대로를 부분 문자열로 찾게 한다.
        phrase = '"' + query.replace('"', '""') + '"'
        sql = (
            f"SELECT project, session, cwd, role, ts, "
            f"snippet(msgs, {_TEXT_COL}, '»', '«', '…', 12) "
            "FROM msgs WHERE msgs MATCH ?"
        )
        params: list = [phrase]
        if project:
            sql += " AND project LIKE ?"
            params.append(f"%{project}%")
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        try:
            return self.conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []  # 그래도 실패하면(빈 질의 등) 결과 없음으로

    def _search_like(self, query: str, project: str | None, limit: int) -> list[tuple]:
        sql = (
            "SELECT project, session, cwd, role, ts, substr(text, 1, 200) "
            "FROM msgs WHERE text LIKE ?"
        )
        params: list = [f"%{query}%"]
        if project:
            sql += " AND project LIKE ?"
            params.append(f"%{project}%")
        sql += " LIMIT ?"
        params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.conn.close()
