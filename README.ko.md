# recall

**여태까지 돌린 모든 Claude Code 세션을 grep 하세요 — 밀리초 만에, 토큰 0으로.**

[English](README.md) · **한국어**

[![CI](https://github.com/dawith-ai/recall/actions/workflows/ci.yml/badge.svg)](https://github.com/dawith-ai/recall/actions/workflows/ci.yml)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-black)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Dependencies](https://img.shields.io/badge/runtime%20deps-0-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

---

**당신의 에이전트는 이미 기억을 갖고 있습니다 — 색인이 안 됐을 뿐입니다.** 여태 돌린 모든 Claude Code 세션이 디스크에 그대로 있습니다. `recall`은 그걸 **소급해서** 색인하고 검색 가능하게 만듭니다. 몇 달 전에 미리 훅을 깔아둘 필요도, "지금부터 기록 시작"도 없습니다. 이력은 이미 거기 있습니다.

이 버그, 석 달 전에 똑같이 풀었는데. 어느 세션에서였지? 기억 안 나고, `~/.claude/projects`를 손으로 뒤지는 건 답이 없습니다.

`recall`은 전체 기록을 전문 검색하게 해줍니다:

```console
$ recall search "oauth 토큰 갱신"
"oauth 토큰 갱신" — 과거 세션 3건:

  [2026-04-12] my-api · assistant
    …»oauth« refresh »토큰«을 키체인에 저장하고 재인증을 게이트로…
    ↳ resume: claude --resume a3f8c9e1-...
```

원하는 걸 찾았으면, 그 세션으로 바로 복귀:

```console
$ recall resume "oauth 토큰 갱신"
# my-api · 2026-04-12
cd /home/you/my-api && claude --resume a3f8c9e1-...
```

## 무엇이 다른가

**토큰 0. 네트워크 0. LLM 0.** `recall`은 로컬 세션 로그를 읽어 평범한 SQLite 인덱스를 만듭니다. 검색은 모델 호출이 아니라 DB 쿼리라 비용이 0이고 오프라인에서 돕니다. 기록은 기기를 떠나지 않습니다.

**메시지 10만 개를 밀리초에.** SQLite FTS5 기반. 실제 세션 5,000개(메시지 약 10만) 아카이브에서 즉시 반환됩니다.

**한국어와 코드가 진짜로 됩니다.** 기본 FTS5는 `인덱스를`을 한 토큰으로 잡아서 `인덱스`로 검색하면 아무것도 못 찾습니다 — 순진한 FTS5 도구가 모두 안고 있는 실제 버그입니다. `recall`은 trigram 인덱스를 써서 한국어 부분 검색도, `foo()` 같은 코드 심볼도 찾습니다.

**검색이 곧 재개.** 모든 결과에 그 세션을 맥락 그대로 이어갈 명령이 붙습니다. `recall resume "<질의>"`는 가장 잘 맞는 세션의 명령을 출력합니다.

**"지금부터"가 아니라 이미 있는 걸 읽습니다.** 에이전트에 기억을 주는 도구들은 보통 설치한 날부터 캡처를 시작합니다. `recall`은 디스크에 이미 쌓인 세션을 읽으므로, 설치하는 순간 몇 달치 이력을 검색할 수 있습니다. (캡처형 기억 도구와도 잘 조합됩니다 — 서로 다른 질문에 답합니다.)

## 설치

```bash
pip install git+https://github.com/dawith-ai/recall
recall index      # 인덱스 생성 (증분 — 재실행은 빠름)
```

또는 클론에서:

```bash
git clone https://github.com/dawith-ai/recall && cd recall
pip install .
```

요구 사항: Python 3.11+. FTS5 지원 SQLite(사실상 모든 파이썬 빌드에 포함). **런타임 의존성 0** — 표준 라이브러리만.

## 사용법

```bash
recall index                       # 새/변경된 세션 색인 (아무 때나 실행)
recall search "비밀번호 재설정"     # 전체 기록 전문 검색
recall search "마이그레이션" -p api  # "api" 매칭 프로젝트로 한정
recall search "깨지는 테스트" -n 20  # 결과 더 보기
recall resume "oauth 갱신"         # 가장 잘 맞는 세션의 재개 명령 출력
recall stats                       # 인덱스 크기 + 활발한 프로젝트
```

새 세션이 쌓이면 언제든 `recall index`를 다시 실행하세요 — 지난번 이후 변경된 파일만 읽어서 계속 빠릅니다.

## 에이전트가 자기 과거를 검색하게 (MCP)

`recall`은 [MCP](https://modelcontextprotocol.io) 서버이기도 해서, Claude가 작업 도중 **자기** 이력을 스스로 검색할 수 있습니다 — "이거 전에 어떻게 했더라"를 당신이 아니라 에이전트가 답합니다.

```bash
claude mcp add recall -- recall serve
```

이제 에이전트는 `search_sessions`·`resume_session` 두 도구를 갖습니다. 이미 해결한 걸 다시 하려 할 때, 먼저 찾아볼 수 있습니다. MCP 서버도 똑같은 의존성 0 파이썬입니다 — 표준 라이브러리만으로 stdio 위에서 JSON-RPC를 말하므로, 설치할 SDK가 없습니다.

## 동작 방식

```
recall index ─► ~/.claude/projects/**/*.jsonl 스캔 (변경된 파일만)
                  │  각 메시지에서 텍스트 추출 (도구 호출 포함)
                  │  실제 cwd 를 읽어 정확한 프로젝트명 부여
                  ▼
                SQLite FTS5 (trigram)   ~/.local/state/recall/index.db
                  ▲
recall search ─► 부분 문자열 질의 ─► 랭킹된 발췌 + 재개 명령
```

프로젝트 라벨은 폴더 이름을 디코딩하는 게 아니라 각 세션에 기록된 실제 `cwd`에서 얻습니다 — Claude의 폴더 인코딩은 되돌릴 수 없어서(`/you/개발` → `-you---`) 디코딩하면 비ASCII 경로가 사라집니다. 실제 cwd를 읽으면 누구의 기기에서든 정확합니다.

## 설계 노트

- **런타임 의존성 0.** 표준 라이브러리만 — 검증할 것도, 깨질 것도 없습니다.
- **순수·테스트된 코어.** 파싱과 프로젝트명 해석은 I/O 없는 순수 함수이고, 인덱싱·검색은 한국어 토큰화 회귀까지 포함해 끝에서 끝까지 검증됩니다. `pytest -q`.
- **mtime 증분.** 변경이 없으면 세션 5,000개 재색인이 거의 즉시 끝납니다.
- **우아한 폴백.** trigram FTS5 → 일반 FTS5 → `LIKE` 순으로, 어떤 SQLite 빌드에서도 동작합니다.

## 더 큰 키트의 일부

`recall`은 Claude Code 에이전트를 무인 운영하기 위한 도구 모음 중 하나로, [afterlimit](https://github.com/dawith-ai/afterlimit)(한도가 풀리면 에이전트를 재개)과 함께합니다. 더 나올 예정입니다.

## 라이선스

[MIT](LICENSE). Anthropic과 제휴하거나 승인받지 않았습니다.
