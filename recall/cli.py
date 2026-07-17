"""recall CLI — 과거 Claude Code 세션을 즉시 검색한다. LLM 0 호출.

    recall index                  세션을 색인 (새/변경된 것만, 빠름)
    recall search "<질의>"        과거 세션에서 검색
    recall search "<질의>" -p foo  특정 프로젝트로 한정
    recall resume "<질의>"        가장 잘 맞는 세션을 잇는 명령을 출력
    recall stats                  인덱스 현황
"""

from __future__ import annotations

import argparse
import re
import sys

from recall import __version__
from recall.config import Config
from recall.index import build_index
from recall.store import SearchHit, Store

__all__ = ["main"]

_WS = re.compile(r"\s+")


def _hits(cfg: Config, query: str, project: str | None, limit: int) -> list[SearchHit]:
    with Store(cfg.db_path) as store:
        return store.search(query, project, limit)


def cmd_index(cfg: Config, args: argparse.Namespace) -> int:
    r = build_index(cfg)
    engine = "FTS5" if r.fts else "LIKE 폴백"
    print(
        f"색인 완료: 신규 {r.new_files} · 갱신 {r.updated_files} 파일 / "
        f"메시지 {r.total_messages}개 ({engine})"
    )
    if r.total_messages == 0:
        print(f"  세션을 찾지 못했습니다. 경로 확인: {cfg.projects_dir}", file=sys.stderr)
    return 0


def cmd_search(cfg: Config, args: argparse.Namespace) -> int:
    hits = _hits(cfg, args.query, args.project or None, args.limit)
    if not hits:
        print(f"'{args.query}' 관련 과거 세션이 없습니다. (먼저 `recall index` 실행)")
        return 0
    print(f"'{args.query}' — 과거 세션 {len(hits)}건:\n")
    for h in hits:
        snip = _WS.sub(" ", h.snippet).strip()
        print(f"  [{h.ts[:10]}] {h.project} · {h.role}")
        print(f"    {snip}")
        print(f"    ↳ resume: claude --resume {h.session}\n")
    return 0


def cmd_resume(cfg: Config, args: argparse.Namespace) -> int:
    hits = _hits(cfg, args.query, args.project or None, 1)
    if not hits:
        print(f"'{args.query}' 와 맞는 세션이 없습니다.", file=sys.stderr)
        return 1
    h = hits[0]
    # 이어서 작업하려면 그 세션의 원래 폴더에서 실행해야 한다
    print(f"# {h.project} · {h.ts[:10]}")
    if h.cwd:
        print(f"cd {h.cwd} && claude --resume {h.session}")
    else:
        print(f"claude --resume {h.session}")
    return 0


def cmd_stats(cfg: Config, args: argparse.Namespace) -> int:
    with Store(cfg.db_path) as store:
        files, msgs = store.counts()
        engine = "FTS5" if store.fts else "LIKE 폴백"
        print(f"인덱스: 파일 {files}개 / 메시지 {msgs}개 / 엔진 {engine}")
        for project, n in store.by_project(8):
            print(f"  {project}: {n}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="recall",
        description="과거 Claude Code 세션을 즉시 전문 검색한다. LLM 0 호출, 토큰 0.",
    )
    p.add_argument("--version", action="version", version=f"recall {__version__}")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("index", help="세션 색인 (증분)").set_defaults(fn=cmd_index)

    for name, help_ in (("search", "과거 세션 검색"), ("resume", "맞는 세션을 잇는 명령 출력")):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("query")
        sp.add_argument("-p", "--project", default="", help="프로젝트로 한정")
        sp.add_argument("-n", "--limit", type=int, default=10, help="결과 개수")
        sp.set_defaults(fn=cmd_search if name == "search" else cmd_resume)

    sub.add_parser("stats", help="인덱스 현황").set_defaults(fn=cmd_stats)

    args = p.parse_args(argv)
    cfg = Config.from_env()
    if not getattr(args, "fn", None):
        p.print_help()
        return 0
    return args.fn(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
