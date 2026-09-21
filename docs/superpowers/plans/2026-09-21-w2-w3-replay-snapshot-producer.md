# W2–W3 Replay and Snapshot Producer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** W2의 보존된 공용 Source outbox만으로 W3 C-01에 검증된 replay batch와 원자 snapshot을 보내 Source별 복구를 수행한다.

**Architecture:** W2 PostgreSQL의 한 read-only `REPEATABLE READ` snapshot에서 Source와 `1..H` 공용 이벤트를 검증·물질화하고 트랜잭션을 닫는다. 순수 payload 조립기, 기존 W3 전송 보안 경계를 공유하는 HTTP client, Source ID를 명시하는 일회성 operator가 그 결과를 W3에 전달한다. 단일 이벤트 재발행, private commit gate, W3/W1 DB는 변경하지 않는다.

**Tech Stack:** Python 3.12, SQLAlchemy 2, PostgreSQL, Pydantic 2, stdlib `http.client`, pytest, Ruff. W3 계약·실행 핀: Service `0c4f01f9537a3129c976fae5e63111a7982c5da6`.

**Spec:** `docs/superpowers/specs/2026-09-21-w2-w3-replay-snapshot-producer-design.md`

## Global Constraints

- W2 public event는 W1 envelope `schema_version="1.0"`, W2 payload `schema_version="w2.source.v1"`을 유지한다. W3 recovery schema는 `"w3-c01/0.2-candidate"`다.
- `H`는 Source 전체의 최고 `aggregate_revision`, `F=0`은 보존 이력 `1..H`를 확인했을 때만 선언한다. `restriction_revision`은 별도 연속 순번이다.
- Replay batch는 revision 오름차순 최대 500건이다. Snapshot의 `versions`와 `restrictions`는 각각 최대 500건이다. W3 HTTP request body 상한은 2,000,000 bytes다.
- `SourceEvent`와 `source_event_to_w3_wire`를 재사용해 event ID, 시각, payload를 유지한다. 누락·변조·불완전 이력을 성공이나 정책 승인으로 바꾸지 않는다.
- DB 읽기 트랜잭션은 외부 HTTP 호출 전에 닫는다. POST는 정확한 응답 확인 전 성공으로 간주하지 않는다. W3의 `index_ack`는 transport receipt가 아니다.
- 운영 보존기간, outbox pruning, 새 projection/migration, 공개 HTTP route, 자동 scheduler, W1/IAM/SQS 배포, 실제 수집 E2E는 이 계획 밖이다.
- `tests/conftest.py`의 승인된 격리 PostgreSQL 게이트를 유지한다. 합성 데이터와 실제 Source 수집을 구분하고, token/URL/body를 오류·출력에 노출하지 않는다.

## Review Focus

1. W3 status가 다른 Source ID 또는 `H`보다 큰 cursor를 보고하면 POST 0회로 멈춘다 — Task 4의 status 불일치 테스트.
2. HTTP 200이라도 필수 status/outcome 필드가 없거나 cursor가 `bool`이면 실패한다 — Task 3의 response parser 테스트.
3. W3가 page를 수락했으나 durable cursor가 진행되지 않으면 무한 재전송 없이 멈춘다 — Task 4의 no-progress 테스트.
4. 2,000,000 bytes를 넘는 replay/snapshot 요청은 전송하지 않는다 — Task 3의 body-boundary 테스트.
5. 유효한 Source의 빈 outbox 또는 gap을 완전한 snapshot으로 포장하지 않는다 — Task 1·2의 empty/gap 테스트.

## File Map

- `src/epick_engine/source_collection/w3_recovery_store.py`: Source 단위 read-only 일관 스냅샷과 모든 공용 event 검증.
- `src/epick_engine/source_collection/w3_recovery_payloads.py`: replay page와 최신 상태 snapshot 순수 조립.
- `src/epick_engine/source_collection/w3_public_transport.py`: 기존 endpoint·TLS·무 redirect 정책을 재사용할 수 있는 bounded GET primitive만 추가; 기존 publish 동작 유지.
- `src/epick_engine/source_collection/w3_recovery_transport.py`: W3 status GET, recovery POST, 엄격한 응답 검증.
- `src/epick_engine/source_collection/w3_recovery_operator.py`: 명시적 `--source-id` 및 `--mode replay|snapshot` CLI와 durable cursor 재개 제어.
- `tests/unit/source_collection/test_w3_recovery_payloads.py`, `test_w3_recovery_transport.py`, `test_w3_recovery_operator.py`: 순수 계약·전송·상태 전이.
- `tests/integration/source_collection/test_w3_recovery_store.py`: 승인된 격리 PostgreSQL의 read snapshot·롤백·원본 불변성.
- `scripts/verify_w2_w3_postgres_http.py`: 고정 W3 checkout에 대한 기존 공동 E2E에 replay/snapshot 복구 검증 추가.
- `docs/w2-w3-recovery-operator.md`: 명령, 자격 증명·게이트, 안전 실패·재실행·미완료 범위 기록.

### Task 1: Read-only Source history and integrity gate

**Files:**
- Create: `src/epick_engine/source_collection/w3_recovery_store.py`
- Create: `tests/integration/source_collection/test_w3_recovery_store.py`
- Inspect: `src/epick_engine/source_collection/persistence.py:125`, `:1097`; `src/epick_engine/source_collection/worker.py:675`

**Interfaces:**
- Consumes: `Source`, `OutboxEvent`, `worker._source_event_from_outbox_row`, `source_event_to_w3_wire`, `Callable[[], Session]`.
- Produces: `RecoveryHistory(source_id: UUID, high_watermark: int, restriction_revision: int, events: tuple[SourceEvent, ...], as_of: datetime)` and `SqlAlchemyRecoveryHistoryStore.load_history(*, source_id: UUID) -> RecoveryHistory`; sanitized `W3RecoveryHistoryError(code: str)`.

- [ ] **Step 1: Write failing PostgreSQL tests.** Mark the file `pytestmark = pytest.mark.approved_postgres`; use the existing `approved_postgres_url` fixture and an isolated schema/migration pattern from `test_source_outbox.py`. Seed a Source and real outbox rows, then test exact `1..H` order, missing Source, empty outbox, missing revision, malformed payload, restriction sequence gap, and unchanged `delivery_state`. Prove a concurrent append after the first SELECT is absent from the read snapshot and a rolled-back append never changes `H`. Two independent reads of unchanged `H`/restriction revision must produce byte-identical snapshot payloads; a future persisted `occurred_at` must remain covered by `as_of`.

```python
history = SqlAlchemyRecoveryHistoryStore(session_factory=session_factory).load_history(
    source_id=source_id
)
assert history.high_watermark == 3
assert [event.aggregate_revision for event in history.events] == [1, 2, 3]
assert [row.delivery_state for row in session.scalars(select(OutboxEvent))] == ["pending"] * 3
```

- [ ] **Step 2: Confirm red.** Run `python -m pytest tests/integration/source_collection/test_w3_recovery_store.py -q` with `EPICK_TEST_DATABASE_APPROVED=1` and an explicitly isolated `EPICK_TEST_DATABASE_URL`; expect import or behavior failures, not a skip. Do not target a production DSN.
- [ ] **Step 3: Implement the minimum store.** In a fresh SQLAlchemy Session, start `session.begin()`, execute `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY` before the first SELECT, select the registered `Source`, then all that Source's `OutboxEvent` rows ordered by `aggregate_revision`. Set `H` from the last row, reject empty history, require `event.aggregate_revision == ordinal` for each ordinal starting at 1, reconstruct each event via `_source_event_from_outbox_row`, and run `source_event_to_w3_wire` before returning. For restriction events, require payload `restriction_revision == next_restriction_revision`. Derive aware UTC `as_of` deterministically from the maximum persisted `occurred_at` among validated events `1..H`, not from the database clock. Materialize immutable Python values, roll back/close the read Session, and never issue a write or HTTP request here.

```python
session = session_factory()
try:
    session.begin()
    session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
    source = session.get(Source, source_id)
    rows = tuple(
        session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.aggregate_id == source_id)
            .order_by(OutboxEvent.aggregate_revision)
        )
    )
finally:
    session.rollback()
    session.close()
```

- [ ] **Step 4: Confirm green and safety.** Rerun the file with the approved DB and `python -m ruff check src/epick_engine/source_collection/w3_recovery_store.py tests/integration/source_collection/test_w3_recovery_store.py`; capture pass/fail without claiming broader integration.
- [ ] **Step 5: Commit this independently reviewable store and its tests.** Stage only the two files; use Korean subject `feat(w2-w3): 복구용 Source 이력 검증 추가`.

### Task 2: Pure replay and atomic snapshot payloads

**Files:**
- Create: `src/epick_engine/source_collection/w3_recovery_payloads.py`
- Create: `tests/unit/source_collection/test_w3_recovery_payloads.py`
- Inspect: W3 pinned `contracts/c01/v0.2-candidate/{replay,snapshot}.schema.json`, `src/w3_knowledge/c01/contracts.py:132-201`.

**Interfaces:**
- Consumes: `RecoveryHistory` from Task 1.
- Produces: `make_replay_batch(history: RecoveryHistory, *, after_cursor: int) -> dict[str, object]`, `make_snapshot(history: RecoveryHistory) -> dict[str, object]`; sanitized `W3RecoveryPayloadError(code: str)`.

- [ ] **Step 1: Write failing pure tests with synthetic `SourceEvent` values.** Exercise `A=0`, `A=H`, `A>H`, negative/bool cursor, 1/500/501 events, and a page containing only revisions `A+1..min(A+500,H)`. Exercise two versions of one `source_version_id`, independent Version IDs, active→cleared restriction of one ID plus another ID, latest observation/null, `as_of >= max(included occurred_at)`, and 500/501 distinct Version or Restriction IDs. Validate successful bodies against the pinned W3 JSON Schemas in the dev test environment; confirm private Job/owner keys are absent.

```python
page = make_replay_batch(history, after_cursor=500)
assert page["after_cursor"] == 500
assert page["high_watermark"] == 501
assert page["retention_floor_cursor"] == 0
assert [event["revision"] for event in page["events"]] == [501]
```

- [ ] **Step 2: Confirm red.** Run `python -m pytest tests/unit/source_collection/test_w3_recovery_payloads.py -q`; expect missing functions or failing assertions.
- [ ] **Step 3: Implement the pure builders.** Serialize with `source_event_to_w3_wire` only. Build replay from `history.events[after_cursor:after_cursor+500]` after strict integer/range checks. For snapshot, fold events in aggregate revision order into dictionaries keyed by `source_version_id` and `restriction_id`, replace each entry with the latest immutable event, retain the latest observation, sort selected events by `revision`, reject either list above 500, use `history.restriction_revision` as R, set `event_cursor=H`, `complete=True`, and `as_of=max(history.as_of, included occurred_at).isoformat()`.

```python
return {
    "schema_version": "w3-c01/0.2-candidate",
    "source_id": str(history.source_id),
    "after_cursor": after_cursor,
    "high_watermark": history.high_watermark,
    "retention_floor_cursor": 0,
    "events": [source_event_to_w3_wire(e) for e in selected],
}
```

- [ ] **Step 4: Confirm green.** Run the focused pytest file and Ruff check/format-check for these two files; reject malformed `RecoveryHistory` inputs rather than emitting an incomplete snapshot.
- [ ] **Step 5: Commit payloads and tests.** Use Korean subject `feat(w2-w3): replay batch와 원자 snapshot 조립`.

### Task 3: Bounded W3 recovery HTTP client

**Files:**
- Modify: `src/epick_engine/source_collection/w3_public_transport.py:68-131` (only shared bounded HTTP GET/config primitive)
- Create: `src/epick_engine/source_collection/w3_recovery_transport.py`
- Create: `tests/unit/source_collection/test_w3_recovery_transport.py`
- Test: `tests/unit/source_collection/test_w3_public_transport.py` (regression, no behavior change)

**Interfaces:**
- Consumes: existing event endpoint URL `EPICK_W3_EVENT_ENDPOINT`, W2 bearer token, optional CA/TLS context, dict payloads from Task 2.
- Produces: `W3RecoveryClient.status(*, source_id: UUID) -> W3RecoveryStatus`, `.replay(*, source_id: UUID, batch: dict[str, object]) -> W3RecoveryStatus`, `.snapshot(*, source_id: UUID, payload: dict[str, object]) -> W3RecoveryStatus`; immutable `W3RecoveryStatus` with `source_id`, `event_cursor`, `required_event_cursor`, `restriction_revision`, `required_restriction_revision`, `outcome: str | None`, `reason`, `history_complete`, `index_ack`; sanitized `W3RecoveryTransportError(code: str)`.

- [ ] **Step 1: Write failing transport tests.** A fake recording transport asserts one authenticated GET to `/c01/v1/status/{uuid}` and POST only to `/c01/v1/replay` or `/c01/v1/snapshot`. Parameterize invalid endpoint (non-loopback HTTP, path/query/userinfo), redirect, timeout, wrong content type, >65,536-byte response, >2,000,000-byte request, JSON object/type mismatch, missing field, wrong Source, invalid schema version, `bool` cursor, 409 conflict, 422/503 authority/storage errors. Assert no credential or response body appears in exception text.

```python
with pytest.raises(W3RecoveryTransportError) as error:
    client.replay(source_id=source_id, batch=oversized_batch)
assert error.value.code == "REQUEST_TOO_LARGE"
assert recording_transport.calls == []
```

- [ ] **Step 2: Confirm red.** Run `python -m pytest tests/unit/source_collection/test_w3_recovery_transport.py -q`.
- [ ] **Step 3: Add bounded GET without changing publisher semantics.** Reuse `_parse_endpoint` and `_StdlibW3HTTPTransport` from `w3_public_transport.py`; add a direct `get(...) -> W3HTTPResponse` whose connection has the same timeout/TLS/no-proxy/no-redirect/read-limit behavior as existing `post`. Keep `W3HTTPTransport`'s existing `post` contract unchanged so publisher fakes remain valid. Derive fixed recovery targets from the validated event endpoint, never from arbitrary URL text.

```python
target = f"/c01/v1/status/{source_id}"
response = self._transport.get(
    scheme=self._endpoint.scheme,
    host=self._endpoint.host,
    port=self._endpoint.port,
    target=target,
    headers={"Authorization": f"Bearer {self._bearer_token}", "Accept": "application/json"},
    timeout=self._timeout,
    ssl_context=self._ssl_context,
    max_response_bytes=MAX_RESPONSE_BYTES,
)
```

- [ ] **Step 4: Implement strict response parsing.** Require HTTP 200 and JSON content type; a 409/422/503 is a sanitized failure, not a recovery receipt. Parse W3 status fields without coercing booleans to ints; check `schema_version`, exact UUID Source ID, nonnegative cursors, `restriction_scope="version"`, and endpoint-specific `outcome` (`INCOMPLETE|REPLAYED` for replay, `SNAPSHOT_APPLIED` for snapshot). Return `index_ack` only as status metadata. Reject any unexpected outcome, missing field or oversized response.
- [ ] **Step 5: Confirm green and commit.** Run both transport unit files, Ruff check/format-check, and the existing single-event publisher tests. Commit the shared primitive, new client, and tests with Korean subject `feat(w2-w3): 제한된 복구 HTTP 전송 추가`.

### Task 4: Durable-cursor recovery operator

**Files:**
- Create: `src/epick_engine/source_collection/w3_recovery_operator.py`
- Create: `tests/unit/source_collection/test_w3_recovery_operator.py`
- Modify: `pyproject.toml:39-42` (one console script entry)

**Interfaces:**
- Consumes: Task 1 `load_history`, Task 2 builders, Task 3 W3 client. No private Job or W3 DB access.
- Produces: `W3SourceRecovery.recover(*, source_id: UUID, mode: Literal["replay", "snapshot"]) -> RecoveryResult` where `RecoveryResult` has `kind: Literal["REPLAYED", "ALREADY_CURRENT", "SNAPSHOT_APPLIED"]`, `source_id: UUID`, `event_cursor: int`, `restriction_revision: int`; and `main(argv: Sequence[str] | None = None) -> int`. CLI: `epick-w2-w3-recover --source-id UUID --mode replay|snapshot`.

- [ ] **Step 1: Write failing operator tests with recording store/client.** Replay 501 events: first page `INCOMPLETE` at cursor 500, second page `REPLAYED` at 501. Assert the next `after_cursor` comes from W3's durable cursor and an interrupted run starts from fresh W3 status without altering W2 events. Cover `A=H` with no POST; wrong Source/status, `A>H`, W3 required cursor/R above local history, pre-existing conflict, a no-progress response, unexpected `SNAPSHOT_REQUIRED`, and failed page stopping before page 2. Snapshot tests cover explicit mode only, W3 cursor/required/restriction watermark greater than local values, exact `SNAPSHOT_APPLIED` receipt, and `index_ack=False` not presented as indexed success.

```python
result = recovery.recover(source_id=source_id, mode="replay")
assert [body["after_cursor"] for body in client.replay_bodies] == [0, 500]
assert result.event_cursor == 501
assert result.kind == "REPLAYED"
```

- [ ] **Step 2: Confirm red.** Run `python -m pytest tests/unit/source_collection/test_w3_recovery_operator.py -q`.
- [ ] **Step 3: Implement fail-closed control.** Load/validate W2 history before the W3 GET, then validate status Source/cursors and `reason != "CONFLICT"`. In replay mode, use reported durable `event_cursor` as A, POST at most one page per loop, require strictly increasing cursor no higher than H, and re-fetch W3 status before a next page. Accept completion only with cursor H, required cursor H, and restriction/required restriction revision equal to the local R. In snapshot mode, require local H/R not below W3 current or required watermarks, send one complete snapshot, and require `SNAPSHOT_APPLIED` with H/R exact. Never infer index readiness from receipt.

```python
history = self._store.load_history(source_id=source_id)
status = self._client.status(source_id=source_id)
if status.source_id != source_id or status.event_cursor > history.high_watermark:
    raise W3RecoveryOperationError("REMOTE_CURSOR_UNSAFE")
```

- [ ] **Step 4: Wire the CLI safely.** Read DB URL and W3 endpoint/token/optional CA from the existing environment variables, create/dispose Engine, print only `{status, source_id, event_cursor}` on success and a constant sanitized error JSON on failure. Require explicit Source UUID; `--mode snapshot` is never automatic fallback from replay. Add the console script to `pyproject.toml`.
- [ ] **Step 5: Confirm green and commit.** Run operator unit tests, the existing outbox operator regression, Ruff, and `python -m mypy src/epick_engine/source_collection/w3_recovery_operator.py` if the repository's strict mypy environment is available. Commit with Korean subject `feat(w2-w3): Source별 복구 operator 연결`.

### Task 5: Pinned W3/PostgreSQL acceptance and operator handoff

**Files:**
- Modify: `scripts/verify_w2_w3_postgres_http.py`
- Create: `docs/w2-w3-recovery-operator.md`
- Create after a successful run: `docs/w2-w3-recovery-e2e-result-2026-09-21.md`, `docs/w2-w3-recovery-e2e-result-2026-09-21.json`; leave the earlier non-recovery E2E result files unchanged.

**Interfaces:**
- Consumes: Task 4 CLI, W3 pinned worktree `0c4f01f...`, isolated PostgreSQL, existing W2 authority HTTP server and W3 C-01 HTTP server.
- Produces: reproducible synthetic local E2E evidence and the exact operator invocation/remaining integration gates.

- [ ] **Step 1: Add failing E2E assertions to the existing isolated-schema harness.** Seed a contiguous W2 outbox while W3 has a gap, invoke the new replay operator, verify W3 cursor catches H and W2 delivery states do not change. Start a new W3 DB, invoke explicit snapshot, verify cursor/R/H and `history_complete=False`, `index_ack=False`; index through W3's operator endpoint and verify `index_ack=True`. Inject a conflicting immutable W3 fact and verify fail-closed; separately test unregistered Source and unavailable SourceAuthority with no false success. Record the W2 product SHA and pinned W3 SHA.

```python
replay_code, replay_result = _recovery_worker(
    w2_env, "--source-id", str(source_id), "--mode", "replay"
)
assert replay_code == 0 and replay_result["event_cursor"] == high_watermark
assert _get_json(status_url, token=w2_token)["event_cursor"] == high_watermark
```

- [ ] **Step 2: Run the isolated joint E2E.** Reuse the script's approved loopback PostgreSQL gate, UUID-named temporary schema, Alembic upgrade, temporary W3 SQLite DB, and `finally` cleanup. Pass the W3 checkout and full pinned SHA; pass the current W2 code SHA. If Docker/PostgreSQL is unavailable, record this test as unrun rather than passing; complete unit checks independently.
- [ ] **Step 3: Write the operator handoff.** Document exact env names, CLI, explicit snapshot risk, expected response states, safe retry after partial page, 500-item and 2,000,000-byte limits, F=0 prerequisite, known 14 unrelated W2 suite failures, and the still-open G-07 retention/W1 deployment/T067–T069 gates. Do not include credentials, live Source content, or raw response body.
- [ ] **Step 4: Run final focused verification.** Execute `python -m pytest tests/unit/source_collection/test_w3_recovery_payloads.py tests/unit/source_collection/test_w3_recovery_transport.py tests/unit/source_collection/test_w3_recovery_operator.py tests/unit/source_collection/test_w3_public_transport.py -q`; the two PostgreSQL integration files with approved isolated DB; `python -m ruff check ...`; `python -m ruff format --check ...`; and the pinned W3 HTTP script. Run full W2 pytest only if time permits, reporting pre-existing failures separately. Check `git diff --check`, changed contract consumers, and no secret-like data in artifacts.
- [ ] **Step 5: Commit evidence and handoff only after verification.** Stage explicit files, use Korean subject `test(w2-w3): 복구 공동 검증과 운영 인계 기록`, and report exact local commit SHA. Push only if separately requested; do not call this W2–W3 deployment or entire T069 completion.

## Self-review gate

- Tasks 1–4 cover every producer, HTTP, transaction, cursor, and failure rule in the approved spec; Task 5 covers pinned W3 and PostgreSQL evidence without conflating synthetic data with live collection.
- Each Review Focus case has a named owning test above. No operation silently changes W2 outbox state or W3 index ACK.
- The `RecoveryHistory` → payloads → HTTP client → operator interfaces are ordered and the two independent integration gates remain explicit.
- Before execution, review the plan against the pinned W3 worktree and actual Engine HEAD; changes in W3 SHA or contract require a new compatibility check, not silent adaptation.
