# PlanForge 작업지시서 (Work Orders)

> **이 문서의 성격**: 설계서(`docs/`)·시스템 프롬프트(`prompts/`)를 **단일 진실 공급원(SSOT)**으로 두고, 그로부터 도출한 **실행 가능한 작업 티켓** 모음이다. 클로드코드가 이 문서의 티켓 하나를 그대로 집어 작업에 착수할 수 있도록 자기완결적으로 작성했다.
>
> 설계와 충돌이 생기면 **항상 설계서·프롬프트가 우선**한다. 이 문서가 틀렸다면 이 문서를 고친다.
>
> ⚠️ **로드맵 주의**: `docs/`에는 명시적 "6단계 MVP 로드맵" 문서가 없다. 아래 P0~P5는 설계서 전반에서 **추론**한 것이며 확정 전 사용자 확인이 필요하다. 단계 정의가 따로 있으면 그에 맞춰 티켓 번호/우선순위를 재배치한다.

---

## 0. 공통 규칙 (Ground Rules) — 모든 티켓에 적용

1. **위치**: 백엔드는 `desktop/planforge/backend/`. (repo 루트 `backend/`는 무관한 네이버 스마트플레이스 도구다. 컨벤션만 참고.)
2. **SSOT 준수**: 시스템 프롬프트는 코드에 복붙하지 않는다. `prompts/` 파일을 런타임 로드하는 `app/services/prompts.py` 경로를 통해서만 사용한다.
3. **컨벤션**: 기존 P0 코드 스타일을 따른다 — SQLAlchemy 2.0 `Mapped`/`mapped_column`, Pydantic v2 스키마는 `camelCase` 필드, 라우터 prefix `/api/v1/...`, 의존성은 `get_db`/`get_current_user`/`get_approved_user`/`require_role`.
4. **비관적 기본값** (설계서 §0): "AI는 틀린 답을 하고 서버는 죽는다"를 전제. 외부/LLM 호출엔 타임아웃·재시도·부분 실패 보존을 넣는다.
5. **에러 규격 통일** (설계서 §api_spec): 에러 응답은 `{"error":{"code":"...","message":"..."}}`. 상태코드 400/401/403/404/429/500 사용. (현재 P0는 FastAPI 기본 `{"detail":...}` — 이를 통일하는 티켓이 **PF-0**다.)
6. **감사 로그**: 민감 동작(생성·수정·승인·삭제)은 `app/services/audit.py`의 `audit.record(...)`로 남긴다.
7. **테스트 필수**: 각 티켓은 Redis/LLM 키 없이 도는 pytest를 추가/갱신한다(인메모리 큐 + `FakeLLMClient`, `tests/conftest.py` 픽스처 재사용). 머지 전 `pytest` 그린.
8. **Definition of Done (공통)**:
   - [ ] 인수 기준 전부 충족
   - [ ] 신규/변경 동작에 대한 테스트 추가, 전체 `pytest` 통과
   - [ ] 설계서 해당 섹션과 모순 없음
   - [ ] `README.md`(백엔드)·필요 시 본 작업지시서 갱신
   - [ ] 감사 로그/에러 규격 규칙 준수

---

## 1. 현재 상태 (P0 — 완료)

- 인증: `POST /api/v1/auth/{signup,login,refresh}`, `GET /me`. JWT(Access/Refresh)+Bcrypt+RBAC. 최초 가입자=admin/approved, 이후=user/pending.
- 비동기 생성: `POST /api/v1/projects` → **202 + jobId** → Redis 큐 → 워커(`app/worker/`) → 출력계약 JSON 파싱 → 9개 `Section` 버전 저장. 파싱 실패 1회 재시도, 적대/유해 입력 `rejected`.
- 프롬프트/LLM: `prompts/` 런타임 로드, Anthropic 실클라이언트 + 키 없으면 `FakeLLMClient` 폴백.
- 모델: `User / Project / GenerationJob / Section / AuditLog`. 큐/LLM 모두 swappable. 테스트 9개 통과.

**미구현 핵심**: 섹션 재수정(`/refine`), 진행률 실시간 알림, 관리자 기능, 과금/사용량/레이트리밋, 통일 에러 규격, 개인정보 파기 정책.

---

## 2. 작업 티켓

> 권장 처리 순서: **PF-0 → PF-1 → PF-2 → PF-3 → PF-4 → PF-5**. PF-0은 다른 티켓의 전제가 되므로 먼저 한다. 각 티켓은 독립 PR 가능.

---

### PF-0 · 공통 에러 응답 규격 통일 (P0 보강) — ✅ 완료

> 구현: `app/core/errors.py`(핸들러) + `app/main.py` 등록. 401/403/404/409/422/500 모두 `{"error":{"code","message"}}`. 테스트 `tests/test_errors.py`.


- **목적/근거**: 설계서 §api_spec — 모든 에러는 `{"error":{"code","message"}}` 단일 규격, 부분 실패·상태코드 정의(체크리스트 #7).
- **선행조건**: 없음.
- **변경 파일**:
  - `app/core/errors.py` (신규) — 공통 예외/핸들러
  - `app/main.py` — `add_exception_handler` 등록
  - 기존 라우터의 `HTTPException(detail=...)` 유지하되 핸들러에서 규격으로 변환
- **상세 작업**:
  1. `HTTPException`/`RequestValidationError`/처리되지 않은 `Exception`을 잡아 `{"error":{"code","message"}}`로 변환하는 핸들러 작성. `code`는 enum 문자열(예: `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `VALIDATION_ERROR`, `RATE_LIMITED`, `INTERNAL`).
  2. 500은 내부 상세를 숨기고 일반 메시지 + 서버 로그에 traceback.
  3. 응답 스키마를 OpenAPI에 문서화.
- **인수 기준**:
  - [ ] 401/403/404/409/422/500이 모두 `{"error":{"code","message"}}` 형태
  - [ ] 기존 테스트가 새 형식에 맞게 갱신되어 통과
  - [ ] 500에서 스택트레이스가 응답 본문에 노출되지 않음
- **테스트**: 잘못된 토큰(401), 권한 없음(403), 없는 리소스(404), 검증 실패(422) 각각 규격 확인.

---

### PF-1 · 섹션 단위 재수정 `/refine` (P1) — ✅ 완료

> 구현: `POST /api/v1/projects/{pid}/sections/{type}/refine`(202+jobId), `GenerationJob.user_request` 컬럼, `processor._process_refine` + `kind` 분기, `FakeLLMClient._refine`. 테스트 `tests/test_refine.py`(버전 증가·타 섹션 불변·rejected·404·409).


- **목적/근거**: 설계서 §8 말미 + `prompts/PlanForge_시스템프롬프트_재수정용.md` — 전체 재생성이 아니라 **대상 섹션 하나만** 새 버전으로 반환. 로더(`prompts.refine_system_prompt`, `prompts.build_refine_input`)와 `Section` 버전 관리는 **이미 구현됨**. 워커 경로와 엔드포인트만 붙이면 된다.
- **선행조건**: PF-0 권장(에러 규격).
- **변경 파일**:
  - `app/schemas.py` — `RefineReq{ sectionType, userRequest }`
  - `app/routers/projects.py` — `POST /api/v1/projects/{pid}/sections/{type}/refine`
  - `app/worker/processor.py` — `process_refine_job(db, job_id)` 추가
  - `app/worker/worker.py` — payload `kind=="refine"` 분기
  - `app/routers/projects.py` 디스패치 — `get_queue().enqueue({"jobId":..,"kind":"refine"})` / inline 분기
- **상세 작업**:
  1. 엔드포인트: 대상 프로젝트·섹션 소유 검증 → `GenerationJob(kind="refine", section_type=type)` 생성 → **202 + jobId** 반환(생성과 동일 패턴).
  2. `process_refine_job`: 현재 `is_latest` 섹션 본문을 `build_refine_input`에 넣어 `refine_system_prompt`로 LLM 호출 → 출력계약 `{status, type, markdown}` 파싱 → 성공 시 해당 type의 새 버전 저장(`_store_sections` 재사용, 기존 demote) → 잡 success. `rejected`/파싱 실패 처리는 생성과 동일 정책(1회 재시도).
  3. `kind=refine`에서는 9개 전부가 아니라 **단일 type만** 검증·저장.
  4. `FakeLLMClient`에 refine 분기 추가: 입력에 `<user_request>`가 있으면 `{"status":"success","type":<type>,"markdown":"...(refined)"}` 반환, 적대 마커면 `rejected`.
- **인수 기준**:
  - [ ] refine 호출 후 해당 섹션 `version`이 +1, 직전 버전은 `is_latest=False`로 보존(이력 유지)
  - [ ] 다른 섹션은 변경되지 않음
  - [ ] 적대적 `userRequest`는 `rejected`, 섹션 미변경
  - [ ] 잘못된 `sectionType`은 404/422
- **테스트**: 정상 refine(버전 증가·타 섹션 불변), 적대 refine(rejected·불변), 존재하지 않는 섹션.

---

### PF-2 · 생성 진행률 실시간 노출 (SSE/WebSocket) (P2) — ✅ 완료 (SSE)

> 구현: `app/services/events.py`(history 기반 버스: Redis 리스트 + 인메모리), 워커가 `running`/`section_saved`/종료 이벤트 발행, `GET /api/v1/projects/{pid}/jobs/{jid}/events`(SSE, `?token=` 또는 헤더 인증). 테스트 `tests/test_events.py`. 실시간성은 폴링 기반 SSE이며, 필요 시 Redis Pub/Sub 라이브 구독으로 고도화 가능.


- **목적/근거**: 설계서 §user_flow·§7 품질기준 — "② 202 jobId → ③ WebSocket 진행률 → ④ 점진 노출". 무거운 작업의 대기 UX.
- **선행조건**: PF-1(섹션 단위 이벤트가 있으면 더 풍부) 권장, 필수는 아님.
- **설계 선택지(택1, 단순함 우선이면 SSE 권장)**:
  - **SSE**: `GET /api/v1/projects/{pid}/jobs/{jid}/events` (text/event-stream)
  - **WebSocket**: `WS /api/v1/projects/{pid}/jobs/{jid}/ws`
- **변경 파일**:
  - `app/services/events.py` (신규) — Redis Pub/Sub 채널 `planforge:job:{jid}` 발행/구독. 인메모리 폴백(테스트).
  - `app/worker/processor.py` — 단계 전환 시 이벤트 발행(`running`, `section_saved:<type>`, `success|rejected|failed`).
  - `app/routers/projects.py` — 스트리밍 엔드포인트.
- **상세 작업**:
  1. 워커가 각 섹션 저장 직후 `events.publish(jid, {type:"section_saved", section:type})` 발행 → 프런트가 점진 노출 가능.
  2. 스트림은 잡이 terminal 상태가 되면 종료 이벤트 후 닫는다.
  3. 인증: 잡 소유자만 구독 가능. 토큰 검증.
  4. 연결 끊김/타임아웃 대비(heartbeat).
- **인수 기준**:
  - [ ] 생성 한 건에서 `running` → `section_saved`×9 → `success` 이벤트가 순서대로 도착
  - [ ] 타 사용자는 구독 403
  - [ ] 폴링(`GET .../jobs/{jid}`)도 여전히 동작(스트림은 보조)
- **테스트**: 인메모리 이벤트 버스로 발행 순서 검증, 권한 검증.

---

### PF-3 · 관리자 기능 (P3) — ✅ 완료

> 구현: `app/routers/admin.py`(`require_role("admin")`). `GET/PATCH /admin/users`(승인/제재·자기강등 방지), `GET /admin/jobs`(상태별 카운트+failureRate), `GET /admin/prompts`(파일명+콘텐츠 해시 버전). 테스트 `tests/test_admin.py`(RBAC 403, 승인→생성 가능, 통계, 필터, 프롬프트 버전).


- **목적/근거**: 설계서 §admin_flow — 사용자 관리(상태 조회·제재), 콘텐츠 모니터링, 시스템 제어(프롬프트 버전 관리), 운영 모니터링(실패율·지표).
- **선행조건**: PF-0.
- **변경 파일**:
  - `app/routers/admin.py` (신규, `require_role("admin")` 가드)
  - `app/schemas.py` — 관리자용 응답 스키마
- **상세 작업(엔드포인트)**:
  1. `GET /api/v1/admin/users` (페이지네이션) — 가입 사용자 목록/상태.
  2. `PATCH /api/v1/admin/users/{id}` — `status` 승인/비활성(`approved`/`disabled`), `role` 변경. 감사 로그 기록.
  3. `GET /api/v1/admin/jobs` — 최근 잡 + 상태 필터, **실패율 지표**(성공/거부/실패 카운트) 집계.
  4. `GET /api/v1/admin/prompts` — 현재 로드된 프롬프트 파일명 + **version(콘텐츠 해시)** 노출(설계서 1.2 "프롬프트 버전 관리"). (편집은 범위 밖 — 파일이 SSOT.)
- **인수 기준**:
  - [ ] 비admin은 모든 admin 엔드포인트에서 403
  - [ ] pending 사용자를 approve하면 그 사용자가 생성 가능해짐
  - [ ] 잡 통계가 실제 DB 집계와 일치
- **테스트**: RBAC 403, 승인 플로우(pending→approved→생성 200), 통계 카운트.

---

### PF-4 · 사용량·과금·레이트 리밋 (P4) — ✅ 완료 (결제 연동 제외)

> 구현: `UsageLog`/`Subscription` 모델, `app/core/ratelimit.py`(Redis+인메모리, swappable), 생성·재수정에 분당 한도 적용→429+`Retry-After`, 워커 `_finish`에서 사용량 적재, `GET /api/v1/usage`(본인·플랜) + `GET /api/v1/admin/usage`(집계). 테스트 `tests/test_usage.py`. 실제 결제(PG)는 의도적으로 범위 외.


- **목적/근거**: 설계서 §db_schema(과금/사용량 시 `usage_logs`·`subscriptions` 누락 금지), §api_spec(429·레이트 리밋), 체크리스트 #6.
- **선행조건**: PF-0, PF-3(사용량 대시보드 연계).
- **변경 파일**:
  - `app/models.py` — `UsageLog`, `Subscription` 모델(설계서 명세 따름; Soft Delete/이력 정책 반영)
  - `app/core/ratelimit.py` (신규) — Redis 기반 토큰버킷/고정창. 인메모리 폴백.
  - `app/routers/projects.py` — 생성 엔드포인트에 레이트 리밋 적용, 초과 시 **429** + 에러 규격
  - `app/worker/processor.py` — 생성 성공/실패 시 `UsageLog` 기록(토큰/잡 수)
- **상세 작업**:
  1. 사용자당 분/일 생성 한도 설정값(`config.py`)로. 초과 429 + `Retry-After`.
  2. 잡 종료 시 사용량 기록(프롬프트 version, 토큰 추정/실제, 결과 상태).
  3. `GET /api/v1/usage` (본인), admin은 전체 집계.
- **인수 기준**:
  - [ ] 한도 초과 시 429 + 에러 규격 + `Retry-After`
  - [ ] 성공/거부/실패 모두 `UsageLog`에 적재
  - [ ] 사용량 조회가 본인 데이터만 반환
- **테스트**: 한도 초과 429, 사용량 적재/집계, 권한 분리.

---

### PF-5 · 내보내기 + 개인정보 파기 정책 (P5) — ✅ 완료

> 구현: `GET /api/v1/projects/{pid}/export?format=md|json`(설계서 §5 순서로 조립·다운로드), `app/services/retention.py`(즉시 파기 PII vs 가명화 보관 분리), `DELETE /api/v1/account`. 테스트 `tests/test_export_account.py`(md/json 순서, 잘못된 포맷 422, PII 파기·로그 보관, 탈퇴 후 로그인 차단).


- **목적/근거**: 설계서 §privacy_law(탈퇴 시 즉시 파기, 단 법정 보관 의무 데이터는 조건 분리), §crud_mapping(Soft Delete/이력), 산출물 활용.
- **선행조건**: PF-3.
- **변경 파일**:
  - `app/routers/projects.py` — `GET /api/v1/projects/{pid}/export?format=md|json` (전체 문서 조립 다운로드)
  - `app/routers/account.py` (신규) — `DELETE /api/v1/account` (회원 탈퇴), 파기 정책 실행
  - `app/services/retention.py` (신규) — 파기 규칙 엔진
- **상세 작업**:
  1. 내보내기: 최신 섹션들을 설계서 §5 순서대로 마크다운/JSON 단일 문서로 조립.
  2. 탈퇴: 개인정보는 즉시 파기/익명화, **법정 보관 의무 데이터(있다면)는 보관 기간 후 파기**로 조건 분리(설계서 §privacy_law 모순 금지 원칙). `deleted_at` Soft Delete + 실제 파기 잡 분리.
  3. 감사 로그에 파기 이벤트 기록.
- **인수 기준**:
  - [ ] export 결과가 전체 섹션(현재 13개)을 설계서 순서로 포함
  - [ ] 탈퇴 후 개인정보 조회 불가, 파기 정책이 보관 의무와 모순되지 않음
- **테스트**: export 포맷/순서, 탈퇴 후 접근 불가.

---

## 3. 백로그 / 오픈 질문 (착수 전 사용자 확인)

- [ ] **로드맵 확정**: 실제 "6단계" 정의가 따로 있는가? 있으면 PF 번호 재매핑.
- [ ] **출력 모드**: 설계서 §5.2 구분자 모드 전환 필요 여부(현재 5.1 JSON 고정).
- [ ] **LLM 모델/예산**: 기본 모델(`claude-sonnet-4-6`)·`max_tokens`·온도 확정, 비용 상한.
- [ ] **콘텐츠 모니터링 수준**: 유해성 필터링을 별도 단계로 둘지(현재는 프롬프트 내 거부에 의존).
- [ ] **실시간 채널**: SSE vs WebSocket 선택.
- [ ] **검증 세트**: 설계서 §10 "아이디어 10개(정상 5 + 적대/빈/유해 5)" 회귀 테스트로 고정할지.

---

## 4. 빠른 참조

| 영역 | 파일 |
|---|---|
| 설정 | `app/core/config.py` |
| 인증/RBAC | `app/core/security.py`, `app/routers/auth.py` |
| 모델 | `app/models.py` (`SECTION_TYPES` 9종) |
| 큐(swappable) | `app/services/queue.py` |
| LLM(swappable) | `app/services/llm.py` |
| 프롬프트 로드/입력계약 | `app/services/prompts.py` |
| 워커/생성코어 | `app/worker/worker.py`, `app/worker/processor.py` |
| 감사 로그 | `app/services/audit.py` |
| 테스트 픽스처 | `tests/conftest.py` (인메모리 DB/큐 + FakeLLM) |

설계 근거: `docs/PlanForge_에이전트_프롬프트_설계서.md`, `prompts/*.md`.
