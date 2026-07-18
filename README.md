# recall

**Grep every Claude Code session you've ever run — in milliseconds, for zero tokens.**

[한국어](README.ko.md)

[![CI](https://github.com/dawith-ai/recall/actions/workflows/ci.yml/badge.svg)](https://github.com/dawith-ai/recall/actions/workflows/ci.yml)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-black)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Dependencies](https://img.shields.io/badge/runtime%20deps-0-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

---

**Your agent already has a memory — it's just not indexed.** Every Claude Code session you've ever run is sitting on disk. `recall` indexes it and makes it searchable, retroactively. No hooks to install months in advance, no "start recording from now." The history is already there.

You solved this exact bug three months ago. In which session? You have no idea, and scrolling `~/.claude/projects` by hand is hopeless.

`recall` gives you full-text search across your entire history:

```console
$ recall search "oauth token refresh"
"oauth token refresh" — 3 past sessions:

  [2026-04-12] my-api · assistant
    …stored the »oauth« refresh »token« in the keychain and gated re-auth…
    ↳ resume: claude --resume a3f8c9e1-...

  [2026-03-28] billing · user
    …the »refresh« flow drops the »token« when the session…
    ↳ resume: claude --resume 7b21d4f0-...
```

Found the one you want? Jump straight back into it:

```console
$ recall resume "oauth token refresh"
# my-api · 2026-04-12
cd /home/you/my-api && claude --resume a3f8c9e1-...
```

## Why it's different

**Zero tokens. Zero network. Zero LLM.** `recall` reads your local session logs and builds a plain SQLite index. Searching is a database query, not a model call — it costs nothing and works offline. Your history never leaves your machine.

**Milliseconds over 100k messages.** Backed by SQLite FTS5. On a real archive of 5,000+ sessions (~100,000 messages) a query returns instantly.

**Korean and code actually work.** Naïve FTS5 tokenizes `인덱스를` as one token, so searching `인덱스` silently finds nothing — a real bug in every plain-FTS5 tool. `recall` uses a trigram index, so substring queries work for Korean, and for code symbols like `foo()` too.

**Search *is* resume.** Every result carries the command to jump back into that exact session with its context intact. `recall resume "<query>"` prints it for the best match.

**Reads what's already there, not "from now on."** Tools that give agents memory typically start capturing the day you install them. `recall` reads the sessions already on your disk — search months of history the minute you install it. (It composes fine with capture-based memory tools; they answer different questions.)

## Install

```bash
pip install git+https://github.com/dawith-ai/recall
recall index      # build the index (incremental — fast on re-runs)
```

Or from a clone:

```bash
git clone https://github.com/dawith-ai/recall && cd recall
pip install .
```

Requirements: Python 3.11+. SQLite with FTS5 (bundled with virtually every Python build). **Zero runtime dependencies** — standard library only.

## Usage

```bash
recall index                       # index new/changed sessions (run anytime)
recall search "reset password"     # full-text search across all history
recall search "migration" -p api   # limit to projects matching "api"
recall search "flaky test" -n 20   # more results
recall resume "oauth refresh"      # print the command to resume the best match
recall stats                       # totals, date range, roles, busiest projects
recall serve                       # run as an MCP server (for the agent itself)
```

Re-run `recall index` whenever you want to pick up new sessions — it only reads files that changed since last time, so it stays fast.

## Let the agent search its own past (MCP)

`recall` is also an [MCP](https://modelcontextprotocol.io) server, so Claude can search its **own** history mid-task — "how did I handle this before?" answered by the agent, not you.

```bash
claude mcp add recall -- recall serve
```

Now the agent has two tools: `search_sessions` and `resume_session`. When it's about to redo something it already worked out, it can look it up first. The MCP server is the same zero-dependency Python — it speaks JSON-RPC over stdio with nothing but the standard library, so there's no SDK to install.

## How it works

```
recall index ─► scan ~/.claude/projects/**/*.jsonl  (only changed files)
                  │  extract text from each message (incl. tool calls)
                  │  read the real cwd → accurate project name
                  ▼
                SQLite FTS5 (trigram)   ~/.local/state/recall/index.db
                  ▲
recall search ─► substring query ─► ranked snippets + resume commands
```

The project label comes from the `cwd` recorded inside each session, not from decoding the folder name — Claude's folder encoding is lossy (`/you/개발` → `-you---`), so decoding it drops non-ASCII paths. Reading the real cwd is accurate for everyone, on any machine.

## Design notes

- **Zero runtime dependencies.** Standard library only — nothing to audit, nothing to break.
- **Pure, tested core.** Parsing and project-name resolution are pure functions with no I/O; indexing and search are covered end-to-end, including the Korean-tokenization regression. `pytest -q`.
- **Incremental by mtime.** Re-indexing 5,000 sessions is near-instant when nothing changed.
- **Graceful fallback.** trigram FTS5 → plain FTS5 → `LIKE`, so it runs on any SQLite build.

## Part of a larger kit

`recall` is one tool in a set for running Claude Code agents unattended, alongside [afterlimit](https://github.com/dawith-ai/afterlimit) (resume your agent when the usage limit resets). More to come.

## License

[MIT](LICENSE). Not affiliated with or endorsed by Anthropic.
