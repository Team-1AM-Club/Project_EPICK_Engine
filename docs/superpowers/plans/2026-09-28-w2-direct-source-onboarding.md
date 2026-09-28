# W2 Direct Source Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** W1의 신규 공식 정적 Source 등록을 W2에서 사전 승인 규칙으로 자동 온보딩하고, W1 READY 확인 후 기존 수집·FINALIZE·W3 전달 경로로 연결한다.

**Architecture:** W1의 기존 direct-registration dispatch는 단일 명령으로 유지하고 URL/기업 근거는 새 보호 조회에서 받는다. W2 PostgreSQL의 versioned 승인 규칙과 Source별 실행 설정을 원자적으로 결속하고, 영속 READY/HELD/REJECTED ACK를 W1이 수락한 뒤 READY만 fetch한다. 기존 W1 private authority, commit-gate, W2 공용 outbox와 W3 이벤트 의미는 유지한다.

**Tech Stack:** Python 3.12, Pydantic, SQLAlchemy/Alembic, PostgreSQL, FastAPI 계약 스키마, Scrapy 정적 수집, SQS, pytest/Ruff/mypy.

**Spec:** `docs/superpowers/specs/2026-09-28-w2-direct-source-onboarding-design.md`

## Global Constraints

- 기준 W2 `feat/crawler` HEAD `00acf408fbc41a47f5e09b8fdab7420cdc4b944c`, migration head `0013_deletion_ack_confirmed`; 새 migration은 이 head를 잇는다. 실행 시 head가 달라졌다면 코드를 쓰기 전에 계획을 재조정한다.
- W1 Company/Source UUID를 W2에서도 그대로 사용한다. URL·기업 식별 근거를 기존 SQS dispatch에 추가하지 않는다.
- 자동 승인은 W2 운영자가 미리 승인한 기업·정확한 HTTPS host·경로·query·유형·권한·limits 규칙에만 적용한다. 규칙 없음/미확인/충돌은 외부 수집 없이 fail-closed다.
- W1 `JOB_POSTING → job_posting`, `COMPANY_PROFILE → company_website`만 매핑한다. W1/W2 canonical URL 불일치를 자동 보정하지 않는다.
- W1 보호 조회와 READY callback은 **제안 계약**이다. W1이 route/schema·fixture SHA를 수락하고 접근 가능한 full SHA로 고정하기 전에는 운영 연동을 활성화하거나 완료라 주장하지 않는다.
- 기존 private-write authority, owner/Project deletion epoch, 429 사용자 재시도, W1 FINALIZE 후 W2 공용 outbox, W3 동일 Source ID를 유지한다.
- RenderedCollector/Playwright, 새 크롤링 대상 확대, 수집·발췌 미허가 사이트, 비밀값/URL/owner ID가 들어간 공유 증거는 범위 밖이다.
- 기존 미커밋 `docs/superpowers/plans/2026-09-23-w2-private-deletion-scope-v2.md`는 사용자 변경이다. 어느 task의 commit에도 포함하지 않는다. 커밋 subject는 기존 한글 Conventional Commit 규칙을 따른다.
- 저장소 기본 검증은 `python -m pytest`, `python -m ruff check src tests migrations`, `python -m ruff format --check src tests migrations`, `python -m mypy src`다. 이 호스트에서 `.venv/Scripts/python.exe`가 실행되지 않으면 `PYTHONPATH=.venv/Lib/site-packages;src`를 설정한 bundled Python으로 동일 모듈을 실행한다. DB 테스트는 승인된 격리 PostgreSQL과 `EPICK_TEST_DATABASE_APPROVED=1`에서만 실행한다.

## Review Focus

- 계열사가 같은 host를 공유하되 법인/경로가 다른 경우: 다른 Company 규칙으로 승인되지 않아야 한다 — Task 2, 5.
- W1/W2 URL 정규화 차이 또는 같은 Company+URL에 다른 Source ID: 기존 Source를 덮지 않아야 한다 — Task 1, 5.
- W1 ACK 200 직후 W2 확인 기록 commit 실패: fetch/SQS delete 없이 동일 digest ACK로 회복해야 한다 — Task 5, 6.
- READY 뒤 규칙 폐기·정책 revision 변경: 이전 READY로 fetch/최신 포인터 승격을 허용하지 않아야 한다 — Task 2, 6.
- W1 조회와 W2 등록 commit 사이 owner/Project 삭제: 신규 private 행과 늦은 fetch가 되살아나지 않아야 한다 — Task 5, 7.

---

## File Structure and Dependency Gate

- `source_onboarding_contracts.py`: W1 metadata, W2 ACK, digest와 목적 유형의 순수 계약.
- `source_onboarding_policy.py`: DB 승인 규칙의 회사·host·경로·query·유형 매칭과 limits 상한 검사.
- `source_onboarding_store.py`: W2 등록/충돌/receipt/ACK outbox의 단일 transaction 경계.
- `source_onboarding_operator.py`: 운영자 전용 규칙 append와 기존 v1 Source 설정의 일회성 DB 이관.
- `w1_source_registration_client.py`: 새 W1 보호 조회·ACK의 bounded HTTPS 호출.
- `source_onboarding_runtime.py`: 현재성 조회, W2 등록, W1 ACK 확인과 fetch 허가를 순서대로 조합.
- 기존 `persistence.py`, `source_runtime_input.py`, `source_runtime.py`, `source_runtime_operator.py`, `private_deletion_v2.py`의 실제 삭제 구현 위치인 `persistence.py`, 관련 contract/schema/fixture/tests만 필요한 만큼 수정한다.
- Task 1의 W1 계약 초안을 W1에 보내고 W1이 보호 route·schema SHA·callback 의미를 확정해야 Task 4와 Task 6의 wire 부분을 완료할 수 있다. Task 2–3 및 순수 W2 store 검증은 그 사이 진행 가능하다. W1 저장소 제품 코드는 이 계획의 소유 범위가 아니다.

### Task 1: W2 계약 모델과 W1 승인 요청

**Files:** Create `src/epick_engine/source_collection/source_onboarding_contracts.py`, `contracts/w2-private/source-registration-ack.schema.json`, `tests/fixtures/w2_source_onboarding/registration-digest-vector.json`, `tests/fixtures/w2_source_onboarding/registration-ack-ready.json`, `docs/w2-w1-new-source-onboarding-contract-request-2026-09-28.md`, `tests/contract/source_collection/test_source_onboarding_contract.py`; modify `contracts/w2-private/artifacts.sha256`.

**Interfaces:** Produce `RegistrationMetadata`, `RegistrationAck`, `parse_registration_metadata(raw: object, dispatch: W1DirectSourceRegistrationDispatch) -> RegistrationMetadata`, `registration_digest(metadata: RegistrationMetadata) -> str`, `map_w1_source_type(value: str) -> SourceType`. W1 lookup schema is a clearly marked proposal until W1 pins its own schema; W2 ACK schema is W2-owned.

- [ ] Write failing contract tests for strict AVAILABLE/UNAVAILABLE fields, exact dispatch/source/company/fence/epoch/input-version binding, canonical UTF-8 digest vector, only the two SourceType mappings, READY positive policy/rule revisions, HELD/REJECTED null revisions, unknown/duplicate JSON key rejection. `test_source_onboarding_contract.py::test_same_source_different_url_is_not_silently_normalized` is a required focus test.
- [ ] Run `python -m pytest tests/contract/source_collection/test_source_onboarding_contract.py -q`; expect failure because models/schema are absent.
- [ ] Implement the named pure interfaces and schema; W2 ACK reason codes are exactly the design spec values. Add a synthetic fixture and SHA256 entry; no real URL or owner data.
- [ ] Re-run the contract file; expect all PASS. Prepare the W1 request document containing the proposed lookup/ACK route, fields, fixture hash and W1-owned exact files, and mark W1 acceptance `PENDING` rather than fabricating a pin. Give the document to the user for W1 delivery; do not send it independently without authorization.
- [ ] Commit only Task 1 paths with `feat: 신규 Source 등록 계약 초안 추가`.

### Task 2: Versioned W2 승인 규칙과 Source별 설정 저장

**Files:** Create `migrations/versions/0014_source_onboarding.py`, `src/epick_engine/source_collection/source_onboarding_policy.py`, `tests/integration/source_collection/test_source_onboarding_storage.py`, `tests/unit/source_collection/test_source_onboarding_policy.py`; modify `src/epick_engine/source_collection/persistence.py`, `tests/unit/source_collection/test_alembic_config.py`, exact-head preflight and tests in `commit_gate_operator.py`, `private_deletion_operator_v2.py`, `source_runtime_operator.py` and their test files.

**Interfaces:** Produce `match_approved_rule(session: Session, metadata: RegistrationMetadata) -> ApprovedRuleMatch | None`, `load_source_runtime_approval(session: Session, source_id: UUID) -> RuntimeSourceConfig | None`, and an immutable `ApprovedRuleVersion`. Add versioned rule head+immutable revision, Source별 approval, private receipt and ACK outbox tables. Rule-head row lock serializes approval with operator revision changes; Source lock serializes policy decision append.

- [ ] Write failing DB tests: empty rule set denies, exact host/path-segment/query/type/company identity matches, prefix sibling and subdomain do not, shared host's wrong subsidiary fails, revoked rule fails, duplicate owner does not append Source policy revision, owner deletion state has a lockable row. Add migration test that 0013→0014 preserves old Source/receipt data.
- [ ] Run the new unit/DB test files against approved isolated PostgreSQL; expect missing schema/functions failures.
- [ ] Implement migration, models and match/load functions. No host wildcard or regex; query defaults deny. Old runtime rows remain readable during one-time transition; absent new per-Source approval is not auto-approved.
- [ ] Re-run files plus exact-head preflight tests; expect PASS and `alembic heads` reporting only `0014_source_onboarding`.
- [ ] Commit Task 2 paths with `feat: 승인 규칙과 Source별 실행 설정 영속화`.

### Task 3: W2 운영자 규칙 append와 기존 설정 이관

**Files:** Create `src/epick_engine/source_collection/source_onboarding_operator.py`, `tests/unit/source_collection/test_source_onboarding_operator.py`, `tests/integration/source_collection/test_source_onboarding_operator_storage.py`; modify `contracts/w2-private/ct15-runtime.md` only if new head mention is required by its exact-head contract.

**Interfaces:** Produce `append_approved_rule(session: Session, manifest: ApprovedRuleManifest) -> ApprovedRuleVersion` and CLI actions `approve-rule`/`import-v1-config`. `approve-rule` requires W2 operator-provided evidence/permissions/limits and increments the locked rule-head revision; `import-v1-config` maps existing approved source config to DB exactly once before v2 global-only runtime config activation.

- [ ] Write failing tests: a valid synthetic manifest makes a rule match, absent evidence or widened host/path/query is rejected, same revision replay is idempotent, concurrent revision proposals cannot both win, import twice changes no Source policy revision, unapproved rule cannot be enabled by user context.
- [ ] Run the two Task 3 test files; expect failure because operator boundary is absent.
- [ ] Implement bounded CLI and DB transaction. No public admin HTTP endpoint, no secret/URL/owner ID output; W1 must arrange the operational DB role and deployment invocation.
- [ ] Re-run tests; expect PASS. Verify a dry-run/import against an isolated copy of v1 config before any deployment data migration.
- [ ] Commit Task 3 paths with `feat: Source 승인 규칙 운영 경계 추가`.

### Task 4: W1 보호 조회와 등록 ACK HTTPS client

**Files:** Create `src/epick_engine/source_collection/w1_source_registration_client.py`, `tests/unit/source_collection/test_w1_source_registration_client.py`; modify `tests/contract/source_collection/test_w1_transport.py` and W1 fixture snapshots only after W1's accepted full SHA/schema hash is available.

**Interfaces:** Produce `W1SourceRegistrationClient.lookup(dispatch: W1DirectSourceRegistrationDispatch) -> RegistrationMetadata | None` and `.acknowledge(ack: RegistrationAck) -> None`. Reuse existing bounded HTTPS transport/TLS validators; exact targets are the design spec paths. Only exact 200+strict ACKNOWLEDGED body succeeds.

- [ ] Obtain W1's accepted route, response/ACK schema, full SHA and fixture hash. If W1 changes the proposed wire, update the design/Task 1 contract and request user review before coding this task.
- [ ] Write failing fake-transport tests: exact target/bearer/CA, no redirects/proxy/retries, oversized/non-JSON/extra fields fail, 403/409 are semantic denial, 503/timeout retryable by caller, wrong command/source/epoch/input version fails. Pin W1 fixture to accepted schema hash.
- [ ] Run Task 4 tests; expect failure because the client is absent.
- [ ] Implement the two methods and sanitized exceptions without inline retry; follow current `w1_lookup_client.py`/`w1_private_deletion_ack_client.py` boundaries.
- [ ] Re-run tests; expect PASS. Commit Task 4 paths with `feat: W1 Source 등록 보호 조회와 ACK client 추가`.

### Task 5: Idempotent 등록 transaction과 ACK 기록

**Files:** Create `src/epick_engine/source_collection/source_onboarding_store.py`, `tests/integration/source_collection/test_source_onboarding_store.py`; modify `src/epick_engine/source_collection/persistence.py` only where existing Source policy writer/helper is reused.

**Interfaces:** Produce `register_direct_source(session: Session, dispatch: W1DirectSourceRegistrationDispatch, metadata: RegistrationMetadata, private_scope: PrivateWriteScope, now: datetime) -> RegistrationAck` and `confirm_registration_ack(session: Session, command_id: UUID, digest: str, now: datetime) -> None`. Source/Company/policy/config + private receipt/outbox are atomic for READY; HELD/REJECTED write private state only.

- [ ] Write failing DB tests for same command/digest replay, same ID/different URL or company/type, same Company+URL/different ID, different owners sharing one public Source, no-rule HELD without public row, deletion epoch race under owner lock, W1 ACK 200 followed by marker DB failure leaves ACK pending.
- [ ] Run Task 5 integration tests against approved isolated PostgreSQL; expect missing operations failure.
- [ ] Implement the two store functions with Source and rule-head locks, W2 deletion row/tombstone checks, unique-conflict interpretation and fixed reason codes. Never store protected URL in private receipt/ACK outbox or share it in logs.
- [ ] Re-run tests; expect PASS. Commit Task 5 paths with `feat: 신규 Source 등록과 ACK 상태를 멱등 저장`.

### Task 6: READY 이전 fetch 차단과 DB 기반 실행 설정

**Files:** Create `src/epick_engine/source_collection/source_onboarding_runtime.py`, `tests/unit/source_collection/test_source_onboarding_runtime.py`; modify `src/epick_engine/source_collection/source_runtime.py:761-1068`, `source_runtime_input.py:99-359`, `source_runtime_operator.py:323-800`, `contracts/w2-private/source-runtime-config.schema.json`, `tests/unit/source_collection/test_source_runtime_router.py`, `test_source_runtime_input.py`, `test_source_runtime_operator.py`.

**Interfaces:** Produce `ensure_direct_registration_ready(dispatch: W1DirectSourceRegistrationDispatch, *, session_factory: SessionFactory, command_lookup_client: W1CommandLookupClient, registration_client: W1SourceRegistrationClient, private_authority_client: PrivateAuthorityClient, clock: Clock) -> RegistrationAck`. Existing W1 command lookup/currentness and private authority precede registration metadata lookup. READY + confirmed W1 ACK is the only route to existing `handle_collection_dispatch`; HELD/REJECTED after confirmed ACK deletes SQS without fetch. New v2 global-only config holds claim lease and execution-limit ceilings; Source-specific config comes from the current DB approval. Import Task 3's legacy configs before switching.

- [ ] Write failing router/provider tests: missing DB approval fails closed, READY callback failure or marker failure never invokes collector/SQS delete, confirmed READY invokes once, HELD/REJECTED invoke zero collectors, 403/409 stop, 503/timeout preserve message, restart/replay reuses receipt, policy revocation after READY prevents fetch, SQS visibility heartbeat survives lookup+callback+collection, 429 still requires user retry.
- [ ] Run Task 6 unit tests; expect failure because the new coordinator/provider is absent.
- [ ] Implement orchestration and v2 global config preflight. Preserve existing Core dispatch behavior and staged-result/commit-gate path; update exact `RuntimeSourceConfigFile.sources` assumptions rather than bypassing them. After policy change post-READY, report an existing policy-stage failure to W1, not a second conflicting ACK for the same command.
- [ ] Re-run Task 6 tests and existing source runtime suite; expect PASS. Commit Task 6 paths with `feat: READY 확인 후 정적 Source 수집 실행`.

### Task 7: 삭제·W3 경계와 공동 회귀

**Files:** Modify `src/epick_engine/source_collection/persistence.py:1363-1570`, `tests/integration/source_collection/test_private_deletion_scope_v2.py`, `tests/contract/source_collection/test_foundation_boundary.py`; create `tests/integration/source_collection/test_source_onboarding_lifecycle.py`, `docs/w2-w1-new-source-onboarding-handoff-2026-09-28.md`.

**Interfaces:** Existing `apply_private_deletion_v2` must classify/purge new owner/Project receipt+ACK rows and preserve shared public Source. Existing FINALIZE/outbox Source identity must remain unchanged. No new W3 READY event is emitted at registration ACK.

- [ ] Write failing integration tests: ACCOUNT/PROJECT deletion purges new private rows, unknown Project scope fails closed, late command after tombstone cannot recreate private state or fetch, another owner's same Source/Version remains, no W3 outbox before FINALIZE, same Source ID and aggregate revision after FINALIZE.
- [ ] Run Task 7 integration/contract files against approved isolated PostgreSQL; expect missing deletion handling or outbox assertion failure.
- [ ] Implement only new private-row deletion ripple and needed W3 identity assertions. Keep public Source/Version/Evidence untouched on another owner's deletion.
- [ ] Re-run relevant tests, Ruff check/format, mypy and Alembic head; expect PASS. Run the full suite and report pre-existing RenderedCollector eight RED and any new failure separately; do not hide unrun AWS/W1/W3 E2E.
- [ ] Commit Task 7 paths with `feat: 신규 Source 등록 삭제 경계와 공동 회귀 보강`.

## Final Handoff Gate

W1이 보호 route/ACK 계약을 승인한 full SHA와 schema SHA256, W2 새 full SHA/head/변경 schema SHA256, W3 pin, 검증 명령·결과, 이미지 실행 시 immutable digest를 handoff에 적는다. 같은 핀에서 W1 공개 API로 **새 승인 정적 URL**을 등록하되 해당 Source/설정은 테스트 전 수동 주입하지 않고 W2 READY→수집→W1 FINALIZE→W3 READY를 관찰한다. 이 공동 실행이나 W1 route 수락이 없으면 W2 로컬 구현 결과만 전달하고 신규 온보딩/T050/T058은 `PENDING`으로 둔다. W1·W3 저장소 변경이나 AWS 배포는 각 담당자의 별도 승인·실행 범위다.
