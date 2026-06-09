# PlanForge Backend (FastAPI)

아이디어 한 줄을 즉시 개발 착수 가능한 **기획·설계 문서**로 변환하는 백엔드.
설계의 단일 진실 공급원은 [`../docs`](../docs)와 [`../prompts`](../prompts)다.

## 현재 구현 범위 (P0 — 1차 작업)

- **인증**: `signup` / `login` / `refresh` / `me` (JWT Access+Refresh, Bcrypt, RBAC)
  - 최초 가입자는 승인된 admin, 이후 가입자는 `pending` → admin 승인 후 생성 가능
- **비동기 생성 파이프라인**: 프로젝트 생성 시 `202 Accepted + jobId` 반환 → Redis 큐 적재 → 워커가 처리
  - 워커: 시스템 프롬프트(`../prompts`) + 입력 계약 조립 → LLM 호출 → JSON 출력 계약 파싱 → 9개 섹션 저장
  - 파싱 실패 시 1회 재시도, 그래도 실패하면 잡 `failed` (설계서 §10)
  - 적대적/빈/유해 입력은 `rejected`로 차단 (설계서 §3 인젝션 방어)
- **프롬프트 연결**: `prompts/` 폴더 파일을 런타임에 읽어 시스템 프롬프트로 주입 (코드에 중복 저장하지 않음). 콘텐츠 해시를 버전 태그로 사용해 잡에 기록.

## 아키텍처

```
Client → FastAPI (routers/projects.py)  --202+jobId-->  Redis Queue (services/queue.py)
                                                              │
                                                     Worker (worker/worker.py)
                                                              │  process_job()
                              prompts/ ──► services/prompts.py ─┤
                              services/llm.py (Anthropic|Fake) ─┤
                                                              ▼
                                              Sections (버전 관리, is_latest)
```

## 실행

```bash
cd desktop/planforge/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # 필요 시 값 조정

# 1) API 서버
uvicorn app.main:app --reload --port 8200

# 2) 워커 (별도 터미널, Redis 필요)
python -m app.worker.worker
```

Redis 없이 단일 프로세스로 돌리려면 `.env`에서 `PLANFORGE_INLINE_DISPATCH=true` (FastAPI BackgroundTasks로 인라인 처리).

LLM API 키(`PLANFORGE_ANTHROPIC_API_KEY`)가 없으면 자동으로 `FakeLLMClient`로 폴백해 파이프라인이 키 없이도 동작한다.

## 테스트

```bash
pytest    # Redis/LLM 키 불필요 — 인메모리 큐 + FakeLLMClient
```

## 주요 API

| 기능 | 메서드 | Endpoint | 인증 | 응답 |
|---|---|---|---|---|
| 회원가입 | POST | `/api/v1/auth/signup` | - | 201 UserRes |
| 로그인 | POST | `/api/v1/auth/login` | - | TokenPair |
| 토큰 갱신 | POST | `/api/v1/auth/refresh` | - | accessToken |
| 내 정보 | GET | `/api/v1/auth/me` | ✓ | UserRes |
| 생성 요청 | POST | `/api/v1/projects` | ✓(승인) | **202** + JobRes |
| 잡 상태 조회 | GET | `/api/v1/projects/{pid}/jobs/{jid}` | ✓ | JobRes |
| 진행률 스트림(SSE) | GET | `/api/v1/projects/{pid}/jobs/{jid}/events` | ✓(토큰/?token=) | text/event-stream |
| 섹션 재수정 | POST | `/api/v1/projects/{pid}/sections/{type}/refine` | ✓(승인) | **202** + JobRes |
| 프로젝트(섹션) 조회 | GET | `/api/v1/projects/{pid}` | ✓ | ProjectRes |
| 프로젝트 목록 | GET | `/api/v1/projects` | ✓ | 페이지네이션 |
| 내 사용량/플랜 | GET | `/api/v1/usage` | ✓ | UsageRes |
| 설정 조회/변경 | GET·PUT | `/api/v1/settings` | ✓ | AI 엔진(provider/모델/키) |
| Ollama 모델 목록 | GET | `/api/v1/settings/ollama/models` | ✓ | 설치 모델 |
| 문서 내보내기 | GET | `/api/v1/projects/{pid}/export?format=md\|json` | ✓ | 다운로드 |
| 문서 파일 저장 | POST | `/api/v1/projects/{pid}/export/save?format=md\|json` | ✓ | `{path,filename,format}` (사이드카가 디스크에 기록) |
| 저장 파일 열기 | POST | `/api/v1/projects/{pid}/export/reveal?format=md\|json` | ✓ | `{revealed}` (탐색기/Finder에서 표시) |
| 회원 탈퇴 | DELETE | `/api/v1/account` | ✓ | 파기/보관 요약 |

> 생성·재수정은 사용자당 분당 레이트 리밋이 걸려 초과 시 **429 + `Retry-After`**.
> 탈퇴 시 개인정보는 즉시 파기, 법적 보관 의무 데이터(사용량·감사 로그)는 가명화 보관(설계서 §privacy_law).

**관리자(admin 전용)**

| 기능 | 메서드 | Endpoint |
|---|---|---|
| 사용자 목록 | GET | `/api/v1/admin/users?status=&page=&page_size=` |
| 사용자 상태/권한 변경 | PATCH | `/api/v1/admin/users/{id}` (status/role, 자기 자신 강등 불가) |
| 잡 현황 + 실패율 | GET | `/api/v1/admin/jobs?status=&page=&page_size=` |
| 사용량 집계 | GET | `/api/v1/admin/usage` |
| 프롬프트 버전 확인 | GET | `/api/v1/admin/prompts` |

모든 에러 응답은 `{"error":{"code","message"}}` 단일 규격(설계서 §api_spec).

## MVP 로드맵 (문서에서 추론 — 확인 필요)

> `docs/`에는 명시적인 "6단계 MVP 로드맵" 문서가 없어, 설계서 전반에서 아래와 같이 추론했다.
> 실제 의도와 다르면 알려주면 맞춘다.

- **P0 (완료)**: 인증 + 비동기 생성 파이프라인 스켈레톤 + 프롬프트 연결
- **PF-0 (완료)**: 공통 에러 응답 규격 통일
- **P1 (완료)**: 섹션 단위 재수정(`/refine`) — `재수정용` 프롬프트 워커 경로 연결
- **P2 (완료)**: 실시간 진행률(SSE) — running → section_saved×9 → 종료 이벤트
- **P3 (완료)**: 관리자 기능 — 사용자 승인/제재, 프롬프트 버전 확인, 운영 모니터링(실패율)
- **P4 (완료)**: 사용량/레이트리밋 — `usage_logs`/`subscriptions`, 분당 한도 초과 시 429(결제 연동은 범위 외)
- **P5 (완료)**: 문서 내보내기(md/json) + 회원 탈퇴(즉시 파기 vs 법정 보관 분리)
