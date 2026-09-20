# W2 FINALIZE Pointer Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** W1의 인증된 collection/direct-registration dispatch를 W2 정적 수집, 공용 불변 저장, private staging에 연결하고, 유효한 FINALIZE에서만 Source 최신 포인터를 안전하게 승격한다.

**Architecture:** 기존 `SourceCollectionWorker`의 same-DB authority 경로와 `apply_commit_gate()`의 private-only 기본 동작은 보존한다. 새 runtime은 W1 원본 dispatch를 immutable하게 보관하고, W2 DB의 Source별 내부 관측 순서와 collection candidate를 사용해 공용 저장과 private staging을 원자 처리한다. collection-aware gate orchestration은 기존 private gate savepoint를 outer transaction에서 호출한 뒤 FINALIZE 포인터 승격을 수행하며, invariant 실패 시 private 상태와 ACK까지 함께 rollback한다.

**Tech Stack:** Python 3.12, Pydantic 2, SQLAlchemy 2, PostgreSQL/psycopg, Alembic, Scrapy 기반 정적 collector, stdlib HTTPS lookup, boto3 SQS adapter, pytest, Ruff, mypy.

**Spec:** `../../../../specs/001-official-source-collection/w2-finalize-pointer-design.md`

## Global Constraints

- W1 원본 `W1Dispatch.payload`와 pin을 lookup, staged-result digest, replay에서 그대로 사용한다. 로컬 effective command는 public collection validation에만 사용하며 W1 wire command로 송신하거나 저장하지 않는다.
- W1이 slot/lease를 확보해 발행한 인증 dispatch와 각 side-effect 직전 fresh `AVAILABLE` lookup을 함께 요구한다. lookup 단독으로 permit, slot, lease를 만들지 않는다.
- 최초 `resume_stage=policy`, `policy_revision=null`만 이 계획의 실행 범위다. non-policy resume은 W1이 실제 policy revision을 보존한 pin을 제공할 때까지 fail-closed다.
- Source별 내부 관측 순서는 W2 DB 내부 값이다. public `aggregate_revision`, `restriction_revision`, W1 `operation_revision`과 비교하거나 wire에 추가하지 않는다.
- Source pointer writer는 내부 `pointer_update_mode`로 단일화한다. 첫 새-runtime reservation이 Source를 `FINALIZE_GATE`로 전환한 뒤 legacy same-DB commit은 그 Source에서 거부되며, 두 경로가 같은 Source 포인터를 동시에 쓰지 않는다.
- 공용 SourceVersion/Evidence/Observation/outbox와 private stage/outbox는 하나의 W2 transaction에 저장한다. 이 transaction에서는 Source 최신 포인터를 갱신하지 않는다.
- `apply_commit_gate()`의 기존 caller와 private-only 의미를 유지한다. collection runtime만 별도 outer orchestrator를 사용한다.
- 현재 policy는 같은 Source의 최대 `SourcePolicyDecision.revision`이다. 수집 revision과 다르면 private FINALIZE는 유지하되 모든 포인터 승격을 보류한다.
- 성공 version 승격은 `official_status=verified`, `access_class=public`, `collection_permission=allowed`, `excerpt_storage_permission=allowed`를 모두 요구한다. 실패 observation은 기존 성공 version을 지우지 않는다.
- ABORT/PURGE는 private candidate lifecycle만 바꾸며 적법한 공용 불변 기록을 삭제하지 않는다. 계정/Project 전체 삭제 완료는 T067 전까지 주장하지 않는다.
- runtime config에 승인된 Source별 robots 판정, 실행 한도, result version이 없거나 DB의 최신 policy revision과 다르면 외부 fetch 전에 중단한다. allow/default 값을 추론하지 않는다.
- execution claim의 획득·만료·갱신·commit 판정은 PostgreSQL `clock_timestamp()`를 단일 시계로 사용한다. worker/container clock은 claim 소유권 판단에 사용하지 않는다.
- claim은 public/private DB commit의 single-writer를 보장하지만 외부 read-only fetch/parent parser의 exactly-once를 주장하지 않는다. Parser는 현재 cooperative cancellation/deadline이 없으므로 heartbeat 상실 뒤 짧은 local overlap이 가능하며, stale token의 결과 폐기와 commit 차단을 안전 경계로 삼는다.
- `SourcePolicyDecision` revision writer와 FINALIZE current-policy reader는 동일한 Source row lock helper를 사용한다. 현재 production writer가 없다는 사실을 동시성 보장으로 대신하지 않으며, helper 밖의 direct `session.add`/flush persistence는 contract test로 금지한다. Caller의 transient model construction 자체는 허용한다.
- 실제 HTTPS/SQS/IAM/image/registry 값, W1 resume 수정, 공동 CT15는 외부 Gate다. 로컬 합성 테스트나 preflight를 배포 성공으로 보고하지 않는다.
- 현재 dirty worktree의 관련 없는 변경을 stage, revert, format하지 않는다. 각 commit checkpoint 전에 `git status`와 파일별 diff ownership을 확인한다. 같은 파일에 선행 사용자/B1 변경이 섞였거나 ownership이 불명확하면 whole-file staging과 commit을 생략하고 overlap을 보고한다. clean ownership이 확인되고 사용자가 그 commit을 명시적으로 승인한 경우에만 해당 task의 정확한 경로를 stage한다.

## Review Focus

- 같은 `command_id`가 다른 dispatch/pin digest로 재전달되면 기존 관측 순서를 재사용하지 않고 conflict로 종료하는지 Task 2에서 검증한다.
- public commit 성공 뒤 private stage/outbox flush가 실패하면 SourceVersion/Evidence/Observation/public outbox까지 모두 rollback되는지 Task 4에서 검증한다.
- 두 owner가 같은 Source를 수집하고 오래된 candidate가 늦게 FINALIZE되어도 latest/current pointer가 역행하지 않는지 Task 5에서 검증한다.
- FINALIZE와 PURGE의 순서, exact replay, collection candidate 손실이 각각 idempotent skip 또는 전체 rollback으로 구분되는지 Task 5에서 검증한다.
- lookup 429/503, non-AVAILABLE, malformed dispatch, resource close 실패에서 fetch·DB commit·queue delete가 0회이고 비밀값이 오류에 노출되지 않는지 Task 6~8에서 검증한다.
- 첫 새-runtime reservation과 legacy commit이 경합해도 Source 잠금과 `pointer_update_mode` 전환으로 한 writer만 mutation 가능한지 Tasks 1, 2, 4에서 검증한다.

---

## File Structure

### New files

- `migrations/versions/0008_collection_runtime_candidate.py` — additive Source order, collection attempt, private stage kind migration.
- `src/epick_engine/source_collection/source_runtime_input.py` — validated Source execution config and SQLAlchemy-backed `CollectionInputProvider`.
- `src/epick_engine/source_collection/source_runtime_store.py` — command reservation, atomic public commit/private stage, candidate lifecycle.
- `src/epick_engine/source_collection/source_runtime_gate.py` — collection-aware commit-gate outer transaction and pointer promotion.
- `src/epick_engine/source_collection/source_runtime.py` — lookup-gated execution context, dispatch handler, mixed/dedicated queue router.
- `src/epick_engine/source_collection/source_runtime_operator.py` — environment parsing, SQS/DB/TLS adapters, preflight and bounded CLI loop.
- `tests/integration/source_collection/test_collection_runtime_storage.py` — migration, reservation, atomic persistence/staging tests.
- `tests/integration/source_collection/test_collection_finalize_pointer.py` — FINALIZE/PURGE/policy/concurrency pointer tests.
- `tests/unit/source_collection/test_source_runtime_input.py` — provider/config fail-closed tests.
- `tests/unit/source_collection/test_source_runtime.py` — lookup-gated execution and original-command preservation tests.
- `tests/unit/source_collection/test_source_runtime_router.py` — sender-first parse, mixed/dedicated routing and deletion tests.
- `tests/unit/source_collection/test_source_runtime_operator.py` — settings/preflight/secret-redaction tests.
- `tests/contract/source_collection/test_source_runtime_build.py` — static image/compose hardening and required-setting contract.
- `tests/contract/source_collection/test_source_policy_writer_contract.py` — production policy writers cannot bypass the shared Source-lock boundary.
- `contracts/w2-private/source-runtime-config.schema.json` — non-secret Source execution config contract.
- `contracts/w2-private/source-runtime.md` — runtime invocation, topology and external Gate boundary.
- `Dockerfile.source-runtime` — immutable Python 3.12 non-root runtime image recipe.
- `compose.source-runtime.yaml` — disabled-by-default local wiring with explicit values only.

### Modified files

- `src/epick_engine/source_collection/persistence.py` — additive models and shared canonical-public persistence helper; legacy commit behavior preserved.
- `src/epick_engine/source_collection/policy.py` — allow zero only for the explicit general retry limit while all other limits remain positive.
- `src/epick_engine/source_collection/commit_gate_store.py` — immutable `stage_kind` argument with `PRIVATE_ONLY` default.
- `src/epick_engine/source_collection/commit_gate_runtime.py` — injectable collection-aware gate applier and staged-send authorization hook; existing defaults unchanged.
- `tests/integration/source_collection/test_private_commit_gate.py` — migration backfill and legacy private-only regression.
- `tests/unit/source_collection/test_commit_gate_runtime.py` — default behavior and optional hooks regression.
- `tests/unit/source_collection/test_policy.py` — zero-retry parsing and all other execution-limit boundaries.
- `tests/unit/source_collection/test_alembic_config.py` — `0008` single-head and metadata parity.
- `pyproject.toml` — `epick-w2-source-runtime` console script only; no new package dependency.
- `../../specs/001-official-source-collection/{plan.md,data-model.md,quickstart.md,tasks.md,validation.md,contracts/README.md` — approved design, execution evidence and remaining Gate synchronization.

---

### Task 1: Add the Durable Collection Runtime Schema

**Files:**
- Create: `migrations/versions/0008_collection_runtime_candidate.py`
- Modify: `src/epick_engine/source_collection/persistence.py`
- Modify: `src/epick_engine/source_collection/commit_gate_store.py`
- Test: `tests/integration/source_collection/test_collection_runtime_storage.py`
- Test: `tests/integration/source_collection/test_private_commit_gate.py`
- Test: `tests/unit/source_collection/test_alembic_config.py`
- Regression: `tests/unit/source_collection/test_commit_gate_runtime.py`
- Regression: `tests/unit/source_collection/test_commit_gate_operator.py`
- Regression: `tests/integration/source_collection/test_commit_gate_operator_storage.py`
- Regression: `tests/integration/source_collection/test_commit_gate_delivery.py`
- Regression: `tests/unit/source_collection/test_ct15_inspection.py`
- Test: `tests/contract/source_collection/test_source_policy_writer_contract.py`

**Interfaces:**
- Produces: `CollectionRuntimeAttempt`, `Source.pointer_update_mode`, `Source.next_observation_order`, `Source.last_promoted_observation_order`, `PrivateCommitStage.stage_kind`.
- Preserves: existing `stage_private_result(session, command, result, *, message_id, occurred_at)` callers remain valid and store `PRIVATE_ONLY`.
- Produces: `lock_private_command(session, command_id)` as the shared short-transaction advisory lock for reservation, stage and gate ordering.
- Produces: `lock_source_policy_scope(session, source_id) -> Source` and `append_source_policy_decision(session, decision) -> SourcePolicyDecision` as the only production policy-writer boundary; FINALIZE uses the same Source row lock helper before reading max revision.

- [ ] **Step 1: Write failing migration and model tests**

Add tests that upgrade an isolated schema from revision `0007_restriction_receipt` to head and assert:

```python
source_columns = {column["name"]: column for column in inspector.get_columns("sources")}
assert source_columns["pointer_update_mode"]["default"] in {
    "'LEGACY_SAME_DB'::character varying",
    "'LEGACY_SAME_DB'::text",
}
assert source_columns["next_observation_order"]["default"] in {"0", "0::bigint"}
assert source_columns["last_promoted_observation_order"]["default"] in {"0", "0::bigint"}
assert isinstance(source_columns["next_observation_order"]["type"], BigInteger)
assert isinstance(source_columns["last_promoted_observation_order"]["type"], BigInteger)
assert "collection_runtime_attempts" in inspector.get_table_names()
attempt_columns = {
    column["name"]: column for column in inspector.get_columns("collection_runtime_attempts")
}
assert isinstance(attempt_columns["observation_order"]["type"], BigInteger)
stage_columns = {
    column["name"]: column for column in inspector.get_columns("private_commit_stages")
}
assert stage_columns["stage_kind"]["nullable"] is False
assert session.scalar(select(PrivateCommitStage.stage_kind)) == "PRIVATE_ONLY"
```

Create a pre-`0008` private stage before upgrade so the test proves backfill rather than only validating a fresh schema. Add metadata parity assertions for the two Source columns, the new table, indexes, FKs, unique constraints, and `stage_kind` check constraint. Assert downgrade is rejected with the repository's explicit destructive-downgrade error.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/source_collection/test_collection_runtime_storage.py tests/integration/source_collection/test_private_commit_gate.py tests/integration/source_collection/test_commit_gate_delivery.py tests/unit/source_collection/test_alembic_config.py tests/unit/source_collection/test_commit_gate_runtime.py tests/unit/source_collection/test_commit_gate_operator.py tests/integration/source_collection/test_commit_gate_operator_storage.py tests/unit/source_collection/test_ct15_inspection.py tests/contract/source_collection/test_source_policy_writer_contract.py -q --tb=short
```

Expected: FAIL because revision `0008_collection_runtime`, model fields, table, and stage kind do not exist.

- [ ] **Step 3: Implement the additive schema**

Add these SQLAlchemy shapes:

```python
class CollectionRuntimeAttempt(Base):
    __tablename__ = "collection_runtime_attempts"

    command_id: Mapped[UUID]
    attempt_id: Mapped[UUID]
    dispatch_digest: Mapped[str]
    owner_ref: Mapped[UUID]
    job_id: Mapped[UUID]
    source_id: Mapped[UUID]
    company_id: Mapped[UUID]
    observation_order: Mapped[int]  # mapped_column(BigInteger, nullable=False)
    effective_policy_revision: Mapped[int]
    state: Mapped[str]
    claim_token: Mapped[UUID | None]
    claim_expires_at: Mapped[datetime | None]
    observation_id: Mapped[UUID | None]
    source_version_id: Mapped[UUID | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

Use `command_id` as primary key, unique `attempt_id`, unique `(source_id, observation_order)`, composite Source/Company and optional Observation/Version same-Source FKs, owner/job indexes, positive order/revision checks, 64-hex digest check, and states `RESERVED`, `PERSISTED`, `FINALIZED`, `INVALIDATED`. Both Source counters and `CollectionRuntimeAttempt.observation_order` use PostgreSQL/SQLAlchemy `BigInteger`; migration and metadata tests must assert the type rather than accepting default `Integer`. `claim_token` and timezone-aware `claim_expires_at` are both null or both non-null, and every state other than `RESERVED` requires both claim fields null. Add `Source.pointer_update_mode` with values `LEGACY_SAME_DB|FINALIZE_GATE`, backfill/default `LEGACY_SAME_DB`, Source counter defaults `0`, checks `0 <= last_promoted_observation_order <= next_observation_order`, and no wire serialization.

Add `stage_kind` with Python/server default `PRIVATE_ONLY` and check `PRIVATE_ONLY|COLLECTION`. Expose the current private `_lock_command` implementation as the shared internal helper `lock_private_command` without changing its advisory namespace or transaction lifetime. Preserve `_lock_command = lock_private_command` as a compatibility alias because the existing relay imports it directly; Task 1 regression tests must prove that import and relay behavior remain valid. Migration order is exactly:

```python
revision = "0008_collection_runtime"
down_revision = "0007_restriction_receipt"
```

Backfill existing `private_commit_stages` to `PRIVATE_ONLY` before applying NOT NULL/check. Keep downgrade explicitly unsupported because it would erase candidate/order semantics.

Change the stage API compatibly to `stage_private_result(session: Session, command: CollectionCommand, result: CollectionResult, *, message_id: UUID, occurred_at: datetime, stage_kind: Literal["PRIVATE_ONLY", "COLLECTION"] = "PRIVATE_ONLY") -> StagedResultProposal`. Do not replace the existing command/result arguments with a proposal argument; current operator and CT15 callers depend on the existing shape. Add `missing_stage_kind: Literal["PRIVATE_ONLY", "COLLECTION"] = "PRIVATE_ONLY"` to `apply_commit_gate`; it is used only when an ABORT/PURGE creates a tombstone before any stage. Existing callers retain `PRIVATE_ONLY`, while the collection outer orchestrator passes `COLLECTION`.

The implementation must bind `stage_kind` on create and include it in immutable replay comparison.

Implement `lock_source_policy_scope` with a SQLAlchemy `select(Source).with_for_update()` query on the Source row. `append_source_policy_decision` locks that scope before adding/flushing the immutable decision. Add an AST-based repository contract test over production `src/epick_engine/source_collection` that rejects direct policy-decision persistence outside this boundary; test fixtures may still seed decisions directly. The bounded source audit found no current production policy writer, so this adds no call-site migration, but future writers cannot bypass the same lock FINALIZE relies on.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: PASS, including pre-`0008` backfill and unchanged legacy private staging.

- [ ] **Step 5: Review diff ownership and prepare the optional schema commit**

Run `git status` and inspect every listed file's diff. If any file contains pre-existing or shared changes, do not stage or commit it; report the overlap. Only after explicit user approval and clean ownership, run:

```powershell
git add migrations/versions/0008_collection_runtime_candidate.py src/epick_engine/source_collection/persistence.py src/epick_engine/source_collection/commit_gate_store.py tests/integration/source_collection/test_collection_runtime_storage.py tests/integration/source_collection/test_private_commit_gate.py tests/integration/source_collection/test_commit_gate_delivery.py tests/unit/source_collection/test_alembic_config.py tests/unit/source_collection/test_commit_gate_runtime.py tests/contract/source_collection/test_source_policy_writer_contract.py
git commit -m "feat: 수집 런타임 후보 저장 구조 추가"
```

---

### Task 2: Reserve Source Observation Order Idempotently

**Files:**
- Create: `src/epick_engine/source_collection/source_runtime_store.py`
- Modify: `tests/integration/source_collection/test_collection_runtime_storage.py`

**Interfaces:**
- Consumes: validated `W1Dispatch`, caller-owned SQLAlchemy `Session` for probe/reservation, a `SessionFactory` for self-contained claim transactions, and `CollectionRuntimeAttempt` from Task 1.
- Produces: `load_bound_collection_attempt(session, dispatch) -> CollectionRuntimeAttempt | None`, `reserve_collection_attempt(session, dispatch, effective_policy_revision, now, uuid_factory) -> CollectionRuntimeAttempt`, `claim_collection_attempt(session_factory, command_id, *, claim_token, lease_seconds) -> CollectionRuntimeAttempt`, `renew_collection_claim(session_factory, command_id, *, claim_token, lease_seconds) -> CollectionRuntimeAttempt`, `release_collection_claim(session_factory, command_id, *, claim_token) -> CollectionRuntimeAttempt`, and `dispatch_digest(dispatch) -> str`.
- Errors: `CollectionRuntimeConflict` for immutable-binding, terminal-state, invalid lease, or lost-token conflicts; `CollectionRuntimeBusy` only when another unexpired claim owns the `RESERVED` row.

- [ ] **Step 1: Write failing reservation tests**

Cover one Source with two owners and assert:

```python
first = reserve_collection_attempt(
    session, first_dispatch, effective_policy_revision=3, now=now, uuid_factory=ids
)
replay = reserve_collection_attempt(
    session, first_dispatch, effective_policy_revision=3, now=now, uuid_factory=ids
)
second = reserve_collection_attempt(
    session, second_dispatch, effective_policy_revision=3, now=now, uuid_factory=ids
)

assert replay.command_id == first.command_id
assert replay.observation_order == first.observation_order == 1
assert second.observation_order == 2
assert source.next_observation_order == 2
```

Also assert same `command_id` with changed pin, company, source, fence, epoch, or job raises `CollectionRuntimeConflict`; a raced/existing `RESERVED` attempt with a different effective policy revision also conflicts. Missing Source, Source/Company mismatch, non-positive policy revision, and a Source row deleted between validation and lock all fail without incrementing the counter.

Persist an attempt at effective revision 3, add DB policy revision 4, and assert `load_bound_collection_attempt` still returns the digest-bound row without consulting current policy. Task 4 owns exact `PERSISTED`/`FINALIZED` durable staged replay; Task 6 owns the execution-layer assertion that a `RESERVED` row's stored effective revision must match the freshly loaded current revision.

Open two PostgreSQL sessions for the same `RESERVED` command. Assert the first self-contained short transaction stores the caller token and DB-clock expiry, the second receives `CollectionRuntimeBusy` without changing state, and no row/transaction lock remains after the claim call returns. Pass a positive `lease_seconds` explicitly; do not read Task 3 configuration or hardcode a lease in this store. Use a test-only SQL update based on `clock_timestamp() - interval '1 second'` to expire the row, then assert a new token can claim and a stale token cannot renew or release. Assert same-token renew is idempotent and release clears only its own active claim. Task 4 owns commit-time stale-token rejection, and Task 5 owns `INVALIDATED` transition plus atomic claim clearing. Python/injected worker clock changes must not affect these outcomes.

Add a gate-first storage-state test: hold the shared command advisory lock, commit an ABORT/PURGE tombstone with `missing_stage_kind="COLLECTION"`, then attempt reservation and assert terminal rejection with the Source counter unchanged. This is a storage fixture, not the production collection-gate orchestrator. Task 5 owns the reservation-first gate race, candidate invalidation, and late-revival proof. Task 4 owns legacy/new-runtime mode checks and their mixed-path race.

- [ ] **Step 2: Run the reservation tests and confirm RED**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/source_collection/test_collection_runtime_storage.py -q --tb=short
```

Expected: FAIL because the reservation API and conflict type do not exist.

- [ ] **Step 3: Implement canonical dispatch binding and reservation**

Define:

```python
class CollectionRuntimeConflict(RuntimeError):
    """The same private command identity was reused with different immutable input."""


class CollectionRuntimeBusy(RuntimeError):
    """Another unexpired DB-clock claim owns this reserved command."""


def dispatch_digest(dispatch: W1Dispatch) -> str:
    payload = dispatch.model_dump(mode="json")
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

`load_bound_collection_attempt` revalidates the concrete dispatch, loads by command ID, and compares the entire canonical dispatch digest without consulting current Source policy. A digest mismatch raises conflict. `reserve_collection_attempt` is itself an idempotent locked operation; callers may probe first, but a replay or race may call reserve when a row already exists. In one short caller-owned transaction it acquires `lock_private_command` first, rejects any existing ABORTED/PURGED private stage before consuming an order, locks/rechecks attempt, then locks Source and validates Source/Company. It transitions `pointer_update_mode` from `LEGACY_SAME_DB` to `FINALIZE_GATE` before incrementing `next_observation_order`, inserting `RESERVED`, flushing and returning. If the locked recheck finds a matching attempt, return it without increment; if it differs, raise conflict. The lock order is always command advisory → attempt → Source. The caller may execute only a `RESERVED` row: later tasks route `PERSISTED`/`FINALIZED` to durable replay and make `INVALIDATED` fail closed. Never derive order from time, W1 `input_version`, event revision, or FINALIZE arrival.

`claim_collection_attempt`, `renew_collection_claim`, and `release_collection_claim` accept a `SessionFactory` and each owns a new Session plus one root transaction, so every row/advisory lock is released before the API returns. Claim and renew require a caller-generated exact token and positive injected `lease_seconds`; read PostgreSQL `clock_timestamp()` inside that transaction and calculate expiry from that DB value. Busy means another token has an unexpired claim; stale/wrong tokens and non-`RESERVED` state are conflicts. Commit-time active-claim validation is added in Task 4, while Task 5 clears claims inside its locked `INVALIDATED` transition. Commit each claim lifecycle call before any collector, parser or queue call. W2 holds no PostgreSQL transaction, row lock, or advisory lock during fetch/parse; crash recovery is explicit DB-clock expiry takeover, not a new W1 slot/lease.

- [ ] **Step 4: Run concurrency and replay tests**

Add a two-session PostgreSQL test that races two different commands for one Source and asserts unique orders `{1, 2}` with `next_observation_order == 2`. Re-run the Step 2 command and expect PASS.

- [ ] **Step 5: Review diff ownership and prepare the optional reservation commit**

Apply the global commit guard. Only after explicit user approval and clean ownership, run:

```powershell
git add src/epick_engine/source_collection/source_runtime_store.py tests/integration/source_collection/test_collection_runtime_storage.py
git commit -m "feat: Source 관측 순서를 멱등 예약"
```

---

### Task 3: Load Approved Source Input Fail-Closed

**Files:**
- Create: `src/epick_engine/source_collection/source_runtime_input.py`
- Create: `contracts/w2-private/source-runtime-config.schema.json`
- Modify: `src/epick_engine/source_collection/policy.py`
- Test: `tests/unit/source_collection/test_source_runtime_input.py`
- Test: `tests/unit/source_collection/test_policy.py`
- Test: `tests/integration/source_collection/test_collection_runtime_storage.py`

**Interfaces:**
- Consumes: `CollectionCommand`, `Source`, max-revision `SourcePolicyDecision`, read-only runtime config.
- Produces: `RuntimeSourceConfigFile`, `SqlAlchemyCollectionInputProvider.load(command) -> StaticCollectionInput`.

- [ ] **Step 1: Write failing config and provider tests**

Use this exact config shape:

```json
{
  "schema_version": "w2.source-runtime-config.v1",
  "claim_lease_seconds": 120,
  "sources": {
    "11111111-1111-4111-8111-111111111111": {
      "policy_revision": 3,
      "robots_permission": "allowed",
      "result_version": 1,
      "language": "ko",
      "redirect_robots_permissions": [],
      "limits": {
        "site_concurrency": 1,
        "global_concurrency": 2,
        "source_ttl_seconds": 300,
        "max_response_bytes": 1048576,
        "max_decompressed_bytes": 2097152,
        "connect_timeout_seconds": 3.0,
        "read_timeout_seconds": 5.0,
        "max_redirects": 2,
        "general_retry_limit": 0,
        "retention_days": 7
      }
    }
  }
}
```

Assert complete strict parsing, duplicate Source rejection, no unknown keys, finite positive `claim_lease_seconds`, finite positive limits except `general_retry_limit == 0`, Source/Company match, max DB policy revision selection, config revision equality, enum mapping, canonical URL/title/type loading, and next public aggregate revision hint from existing outbox state. Extend `test_policy.py` to prove zero is accepted only for `general_retry_limit`; negative retry and zero/negative values for every other integer/float limit remain rejected. Validate the claim lease is strictly greater than the collector child fetch hard deadline plus connect and read timeouts for every configured Source. Derive a non-configurable heartbeat interval no greater than one third of the lease; the heartbeat continues through the separate parent parser rather than pretending that parser is covered by the collector child deadline. Missing config, stale config revision, missing policy, unverified/unregistered Source, or command non-policy/null must fail before collector invocation.

- [ ] **Step 2: Run provider tests and confirm RED**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/source_collection/test_source_runtime_input.py tests/unit/source_collection/test_policy.py tests/integration/source_collection/test_collection_runtime_storage.py -q --tb=short
```

Expected: FAIL because runtime config and provider do not exist.

- [ ] **Step 3: Implement strict config and provider**

Define strict Pydantic models with `extra="forbid"`, exact schema version, UUID-key normalization, and `SecretStr` nowhere in this non-secret file. Update existing `parse_execution_limits` so `_NONNEGATIVE_LIMIT_FIELDS = {"general_retry_limit"}` accepts integer zero while all `_POSITIVE_INTEGER_LIMIT_FIELDS` and float limits remain strictly positive; reject bool for every numeric field. Parse runtime limits only through this shared function and permissions through existing enums.

`SqlAlchemyCollectionInputProvider.load` opens a short read transaction and selects:

```python
policy = session.scalar(
    select(SourcePolicyDecision)
    .where(SourcePolicyDecision.source_id == command.source_id)
    .order_by(SourcePolicyDecision.revision.desc())
    .limit(1)
)
```

It validates Source/Company and exact config revision, then maps all six policy axes to the existing `Policy` contract. `result_version` comes only from the approved config. `aggregate_revision` is the next DB outbox revision hint and is not the internal observation order; Task 4 reassigns the authoritative revision under Source lock before persistence.

- [ ] **Step 4: Verify schema examples and focused tests**

Run the Step 2 command and validate the JSON example against `source-runtime-config.schema.json` in the test. Expected: PASS.

- [ ] **Step 5: Review diff ownership and prepare the optional input-boundary commit**

Apply the global commit guard. Only after explicit user approval and clean ownership, run:

```powershell
git add src/epick_engine/source_collection/source_runtime_input.py src/epick_engine/source_collection/policy.py contracts/w2-private/source-runtime-config.schema.json tests/unit/source_collection/test_source_runtime_input.py tests/unit/source_collection/test_policy.py tests/integration/source_collection/test_collection_runtime_storage.py
git commit -m "feat: 승인된 Source 실행 입력 로드"
```

---

### Task 4: Persist Public Evidence and Private Stage Atomically

**Files:**
- Modify: `src/epick_engine/source_collection/persistence.py`
- Modify: `src/epick_engine/source_collection/source_runtime_store.py`
- Modify: `tests/integration/source_collection/test_collection_runtime_storage.py`
- Regression: `tests/integration/source_collection/test_atomic_persistence.py`

**Interfaces:**
- Consumes: original `W1Dispatch`, reserved attempt, local effective command, `PreparedCollectionCommit`.
- Produces: `commit_collection_candidate(session_factory, dispatch, effective_command, prepared, *, claim_token: UUID, staged_message_id: UUID, occurred_at: datetime) -> StagedResultProposal` and `replay_staged_collection(session_factory, dispatch) -> StagedResultProposal`.
- Preserves: `commit_prepared_collection` legacy same-DB pointer and `CollectionAttempt` behavior.

- [ ] **Step 1: Write failing atomic commit tests**

Assert a successful commit creates canonical SourceVersion/Evidence/Extraction/Observation/public outbox, binds the reserved attempt, and creates a `COLLECTION` private stage/outbox, while all Source pointer fields and `last_promoted_observation_order` remain unchanged.

Add mixed-path tests for one Source. A legacy commit that locks the Source before the first reservation may complete; the later reservation switches mode and becomes the new ordering baseline. Once reservation commits `FINALIZE_GATE`, a delayed or new legacy `commit_prepared_collection` must fail before public or pointer mutation. A candidate commit must reject a Source whose mode is not `FINALIZE_GATE`. Race both paths and assert the Source lock serializes the mode decision so both writer modes cannot succeed after transition.

Preload a Source in the legacy Session, commit a reservation from another Session, and assert the later legacy commit refreshes the locked Source and rejects `FINALIZE_GATE` before any public or pointer mutation. Also race a policy writer between provider load and reservation: `reserve_collection_attempt` must re-read max Source policy revision while holding its Source lock and reject a stale supplied revision without changing mode or consuming an observation order.

Seed an intentionally stale Task 3 aggregate-revision hint and a different internal observation order. Assert new public events receive authoritative Source aggregate revisions from the locked DB maximum, existing event IDs preserve their stored revision, and neither hint nor observation order crosses into `OutboxEvent.aggregate_revision`.

Inject failure separately after canonical public flush, public outbox insert, staged proposal build, and private stage flush. After each failure assert zero new public rows, zero private stage/outbox rows, and attempt state remains `RESERVED` with its active claim intact. Pass stale, expired and wrong claim tokens and assert failure before any public/private write or delivery-marker mutation. On success, assert the exact validated claim is cleared atomically as state becomes `PERSISTED`. Verify the staged proposal contains the exact original dispatch command, not the local effective command. Seed `PERSISTED` and `FINALIZED` attempts and assert `replay_staged_collection` acquires the shared command advisory lock, then reloads attempt/stage/outbox and returns the exact stored proposal/message identity, resets only its delivery marker, performs no fetch/public write, and rejects corrupt/missing payload. When terminal ABORT/PURGE acquires the command lock first, replay must not re-arm or return a proposal. When replay/relay already owns the lock, that in-flight operation may finish, but the later terminal transition must remove durable payload and prevent every subsequent replay/delivery; the actual send-order race remains a Task 7 relay regression. Assert `INVALIDATED` never replays.

- [ ] **Step 2: Run atomic tests and confirm RED**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/source_collection/test_collection_runtime_storage.py tests/integration/source_collection/test_atomic_persistence.py -q --tb=short
```

Expected: FAIL because no collection candidate commit function exists.

- [ ] **Step 3: Extract a shared canonical-public helper**

Refactor only the validation/canonicalization/event portion of `commit_prepared_collection` into a helper used by both paths:

```python
@dataclass(frozen=True, slots=True)
class CanonicalPublicCommit:
    source: Source
    prepared: PreparedCollectionCommit
```

Add `persist_canonical_public_commit(session: Session, *, command: CollectionCommand, prepared: PreparedCollectionCommit) -> CanonicalPublicCommit` with the behavior below.

The helper locks Source with a fresh read (`populate_existing=True` or equivalent), checks Source/Company, policy, retained body and origin targets, canonicalizes entities, and allocates authoritative Source aggregate revisions under the Source lock. Before `_resolve_outbox_event`, replace each new event object's `aggregate_revision` with the allocated DB value so no precommit hint or internal observation order crosses the public boundary; an existing event ID keeps its existing DB revision. The legacy caller then applies its existing `grant.pointer_eligible`, creates `CollectionAttempt`, and returns unchanged behavior.

Before any legacy canonical/public/pointer mutation, `commit_prepared_collection` must require the freshly locked `source.pointer_update_mode == "LEGACY_SAME_DB"`. The new candidate path must require `FINALIZE_GATE`. The check occurs after locking and refreshing Source, so a concurrent first reservation and legacy commit serialize even when the caller Session preloaded Source; no runtime mode silently falls back to the other writer. Preserve the public signatures and behavior of `commit_prepared_collection`, `replay_committed_collection`, `_replay_attempt`, `stage_private_result`, and `_lock_command is lock_private_command`.

While the reservation path holds its fresh Source lock, select the max `SourcePolicyDecision.revision` for that Source and require it to equal the supplied effective policy revision before changing mode or allocating order. This closes the provider-load → reservation race without holding any DB lock during fetch; policy changes after reservation remain a Task 5 FINALIZE promotion guard.

- [ ] **Step 4: Implement atomic candidate commit**

Within one `session.begin()`:

1. lock and validate the reserved attempt against original dispatch digest, owner/job/source/company, attempt ID, effective policy revision, exact caller `claim_token`, and an expiry later than fresh PostgreSQL `clock_timestamp()`;
2. validate `prepared` against the local effective command;
3. call `persist_canonical_public_commit`;
4. bind canonical observation/version, clear `claim_token` and `claim_expires_at`, and set attempt state `PERSISTED` in the same root transaction;
5. build staged result from the original W1 command and canonical `CollectionResult`;
6. call `stage_private_result(session, dispatch.payload, canonical.result, message_id=staged_message_id, occurred_at=occurred_at, stage_kind="COLLECTION")`;
7. flush without touching Source pointers.

Acquire `lock_private_command` before the attempt and Source locks in this transaction. The nested `stage_private_result` call re-enters the same transaction advisory lock and must not reverse the order.

`replay_staged_collection` also starts a short transaction with `lock_private_command`, then reloads and validates attempt, immutable private stage/outbox proposal, terminal receipt and delivery marker in command → attempt/stage/outbox order. Only a still-replayable `PERSISTED`/`FINALIZED` row may re-arm its existing undelivered record. ABORT/PURGE/INVALIDATED already observed under that lock wins and cannot be revived from a proposal read before locking. A replay/relay that acquired the lock first may finish; the following terminal transition must still make all later replay impossible. Replay never invokes provider/collector/public persistence and never allocates a new order.

Re-run Step 2. Expected: PASS, including legacy atomic persistence. Also run the high-fanout legacy regression suites for worker, job-posting/import, recovery, retention, restrictions, static slice, version history and version persistence because `commit_prepared_collection` is their shared default boundary.

- [ ] **Step 5: Review diff ownership and prepare the optional atomic-boundary commit**

Apply the global commit guard. Only after explicit user approval and clean ownership, run:

```powershell
git add src/epick_engine/source_collection/persistence.py src/epick_engine/source_collection/source_runtime_store.py tests/integration/source_collection/test_collection_runtime_storage.py tests/integration/source_collection/test_atomic_persistence.py
git commit -m "feat: 공용 근거와 private stage 원자 저장"
```

---

### Task 5: Promote Pointers Only Inside Valid FINALIZE

**Files:**
- Create: `src/epick_engine/source_collection/source_runtime_gate.py`
- Modify: `src/epick_engine/source_collection/persistence.py`
- Test: `tests/integration/source_collection/test_collection_finalize_pointer.py`
- Regression: `tests/integration/source_collection/test_private_commit_gate.py`
- Regression: `tests/contract/source_collection/test_source_policy_writer_contract.py`

**Interfaces:**
- Consumes: existing `CommitGateCommand`, `apply_commit_gate`, collection attempt and Source rows.
- Produces: `apply_collection_commit_gate(session, gate_command, ack_message_id, occurred_at) -> CommitGateAckProposal`.

- [ ] **Step 1: Write failing FINALIZE state-machine tests**

Cover:

- PREPARE keeps all pointers unchanged.
- valid successful FINALIZE promotes latest observation, current version, first/last collected time from `observation.observed_at`, and last promoted order atomically with ACK.
- valid failure FINALIZE promotes latest observation/order but preserves existing current version and collection times.
- older candidate late FINALIZE returns APPLIED without pointer rewind.
- exact FINALIZE replay does not re-promote; post-FINALIZE PURGE removes private payload/candidate association without public deletion; replay after PURGE returns stored ACK and does not promote.
- ABORT and pre-FINALIZE PURGE invalidate candidate, clear any active claim atomically, and do not promote; the stale worker cannot renew, release or persist.
- max policy revision change, missing current policy, or collection revision mismatch leaves all pointers unchanged while private FINALIZE and ACK persist.
- policy-equal success with any required axis not authorized does not promote current version.
- collection-backed FINALIZE with missing/corrupt candidate, wrong Source/Company, wrong Observation/Version FK, or missing observation rolls back stage state and ACK.
- candidate/public policy binding mismatch (same Source but wrong policy decision or revision), staged proposal command mismatch, gate/stage fence/epoch/digest mismatch, or Source mode other than `FINALIZE_GATE` is an invariant failure that rolls back stage, ACK, candidate and pointers together.
- gate-first ABORT/PURGE with no stage creates a `COLLECTION` tombstone; when a RESERVED candidate already exists it becomes `INVALIDATED`, and when gate wins the race a later reservation is rejected before order allocation.
- `PRIVATE_ONLY` stages retain existing gate behavior and never inspect public candidates.
- two owners on one Source finalize order 2 then 1 and remain at order 2.
- a policy revision writer using `append_source_policy_decision` races FINALIZE in both lock orders: FINALIZE either sees the old revision before the writer or the new revision after it, never promotes from a stale max-revision read concurrent with an unlocked insert.
- preload Source in the caller Session, finalize a newer order elsewhere, then process an older candidate and prove the shared Source policy lock refreshes identity-map state so pointers never rewind.
- force a candidate invariant failure after the private gate savepoint, catch the exception in the caller, commit the outer Session, and prove PREPARED stage/ACK/candidate/pointers all remain unchanged.

- [ ] **Step 2: Run gate tests and confirm RED**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/source_collection/test_collection_finalize_pointer.py tests/integration/source_collection/test_private_commit_gate.py -q --tb=short
```

Expected: FAIL because the collection-aware gate orchestrator does not exist.

- [ ] **Step 3: Implement the outer transaction orchestrator**

Use this decision order:

```python
def apply_collection_commit_gate(
    session: Session,
    gate_command: CommitGateCommand,
    *,
    ack_message_id: UUID,
    occurred_at: datetime,
) -> CommitGateAckProposal:
    with session.begin_nested():
        ack = apply_commit_gate(
            session,
            gate_command,
            ack_message_id=ack_message_id,
            occurred_at=occurred_at,
            missing_stage_kind="COLLECTION",
        )
        stage = session.get(PrivateCommitStage, gate_command.command_id, populate_existing=True)
        if stage is None or stage.stage_kind == "PRIVATE_ONLY":
            return ack
        apply_collection_candidate_transition(session, gate_command, stage)
        session.flush()
        return ack
```

The outer savepoint is mandatory even though `apply_commit_gate` has its own nested boundary: if any collection invariant fails and the caller catches the exception then commits, the private stage/ACK and public transition must still have rolled back together. Do not catch invariant exceptions inside this boundary.

`apply_collection_candidate_transition` must:

1. skip PREPARE;
2. for gate-first ABORT/PURGE with no candidate, retain the `COLLECTION` stage tombstone and return successfully;
3. mark an existing ABORT candidate `INVALIDATED`, clear claim token/expiry and observation/version associations;
4. mark an existing PURGE candidate `INVALIDATED`, clear claim token/expiry and observation/version associations while retaining the command/digest/order tombstone needed to reject command replay; preserve all public rows;
5. for FINALIZE, skip when the stored stage is already PURGED, otherwise retain the command advisory lock, lock candidate with a fresh `FOR UPDATE` read, then lock Source; the global order is command → candidate → Source;
6. load the unique staged outbox under the same lock, strict-parse `StagedResultProposal`, and validate gate↔stage owner/job/fence/epoch/digest plus proposal command↔candidate command/owner/job/source/company and all referenced observation/version bindings;
7. select max policy revision while Source remains freshly locked through the same `lock_source_policy_scope` helper required by every production policy writer; update that helper to use `populate_existing=True` and require `pointer_update_mode == "FINALIZE_GATE"`;
8. require the observation policy decision (when present) and every successful version policy decision to belong to the same Source and exact `candidate.effective_policy_revision`; require observation/source-version/candidate version IDs to agree;
9. return without mutation when an exact replay finds candidate state `FINALIZED`, otherwise mark candidate `FINALIZED` even when current max policy mismatch or older order causes promotion skip;
10. promote only when `candidate.observation_order > source.last_promoted_observation_order` and current max policy revision matches;
11. update current version/timestamps only for a successful version and exactly the four required axes: verified official status, public access, collection allowed and excerpt storage allowed. Body/redistribution are not promotion prerequisites.

Do not catch invariant exceptions inside the outer transaction. The exception must rollback the nested private gate savepoint, ACK, pointer, and candidate transition together.

- [ ] **Step 4: Run gate and concurrency tests**

Run the Step 2 command. Expected: PASS with no behavior change in legacy private-only tests.

- [ ] **Step 5: Review diff ownership and prepare the optional FINALIZE commit**

Apply the global commit guard. Only after explicit user approval and clean ownership, run:

```powershell
git add src/epick_engine/source_collection/source_runtime_gate.py src/epick_engine/source_collection/persistence.py tests/integration/source_collection/test_collection_finalize_pointer.py tests/integration/source_collection/test_private_commit_gate.py tests/contract/source_collection/test_source_policy_writer_contract.py
git commit -m "feat: FINALIZE에서 Source 포인터 원자 승격"
```

---

### Task 6: Execute Initial POLICY Dispatch Through Fresh Lookups

**Files:**
- Create: `src/epick_engine/source_collection/source_runtime.py`
- Modify: `src/epick_engine/source_collection/source_runtime_store.py`
- Test: `tests/unit/source_collection/test_source_runtime.py`
- Regression: `tests/integration/source_collection/test_collection_runtime_storage.py`
- Regression: `tests/unit/source_collection/test_worker.py`
- Regression: `tests/unit/source_collection/test_w1_lookup_client.py`

**Interfaces:**
- Consumes: `W1Dispatch`, `W1LookupClient`, input provider, `StaticCollectionExecution`, store functions from Tasks 2 and 4.
- Produces: `LookupGatedExecutionContext` and a `handle_collection_dispatch` function returning `StagedResultProposal`.

- [ ] **Step 1: Write failing lookup-gated execution tests**

Assert fresh lookup occurs before reservation, POLICY, FETCH, PARSE and PERSIST. For each boundary, return `NOT_FOUND`, `STALE_FENCE`, `STALE_DELETION_EPOCH`, `DELETED`, `INVALIDATED`, or `EXPIRED` and assert all later external/public/candidate/stage/outbox operations are zero. Initial lookup/malformed failure performs no DB write; a failure after reservation/claim may retain the reservation and commit a same-token release but still creates no public/candidate/stage/outbox/ACK. Assert HTTP 429/503 and malformed response are not retried automatically. The actual staged DELIVER lookup belongs to Task 7's durable before-send hook.

Test `resume_stage=policy` with null wire revision: provider selects revision 3, local execution sees a derived effective command with revision 3, but every lookup request, dispatch equality check, staged proposal command, digest, and saved dispatch digest use the untouched original null-policy command. Assert non-policy commands remain rejected until a positive revision arrives from W1. Race a policy writer between provider load and reservation; the Source-locked reservation recheck must reject stale revision 3 without mode/counter mutation. A change after reservation is handled by Task 5's promotion-skip rule. Redeliver the same command in `PERSISTED` and `FINALIZED` state after current policy advances to revision 4 and assert exact durable staged proposal replay with zero provider/collector/public writes and no new observation order. Redeliver an `INVALIDATED` command and assert fail-closed with zero side effects. Redeliver a `RESERVED` revision-3 attempt after current policy advances to 4 and assert no fetch until W1 issues a new command. Race two handlers for one `RESERVED` command and assert collector invocation count is one while the claim remains healthy; the busy handler leaves its queue receipt undeleted. Simulate process death after claim, expire the claim with a DB-clock SQL seam, and assert takeover succeeds without a long DB transaction. Run fetch and the separate parent parser longer than one heartbeat interval and assert renewals prevent takeover. Then invalidate or fail one renewal and assert active fetch cancellation when applicable, stale parser result discard, and no candidate commit/send/delete. Treat local overlap after lease loss as allowed and assert that only the current token can persist. Skew injected worker clocks in both directions and assert they cannot cause early or late takeover.

Force collector/parser/commit exceptions and assert execution resources close once before error propagation. On known precommit failure, stop/join heartbeat, close resources, then release the exact token only when cleanup succeeds. If `close()` fails or child termination is unconfirmed, create no public/candidate/stage/outbox/ACK, do not eagerly release the claim, and permit takeover only after DB-clock expiry.

- [ ] **Step 2: Run runtime tests and confirm RED**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/source_collection/test_source_runtime.py tests/unit/source_collection/test_worker.py tests/unit/source_collection/test_w1_lookup_client.py -q --tb=short
```

Expected: FAIL because the general lookup-gated handler does not exist.

- [ ] **Step 3: Implement immutable-original and local-effective contexts**

Define:

```python
@dataclass(slots=True)
class LookupGatedExecutionContext:
    dispatch: W1Dispatch
    lookup_client: W1LookupClient
    _effective_command: CollectionCommand

    @property
    def command(self) -> CollectionCommand:
        return self._effective_command

    def enter_stage(
        self,
        stage: CollectionStage,
        *,
        policy_revision: int | None = None,
    ) -> object:
        response = self.lookup_client.lookup_dispatch(self.dispatch)
        require_available(response)
        if policy_revision is None:
            raise RuntimeAuthorizationError("runtime stage requires effective policy revision")
        payload = self.dispatch.payload.model_dump(mode="python")
        payload.update({"resume_stage": stage, "policy_revision": policy_revision})
        self._effective_command = CollectionCommand.model_validate(payload)
        return response
```

The POLICY call keeps the local resume stage at POLICY so `StaticCollectionExecution` still enters the FETCH boundary before network access; FETCH and PARSE advance only the local copy. The derived command is never assigned back to `dispatch`, never passed to `lookup_dispatch`, and never used in `build_staged_result`.

Expose a keyword-only injectable handler/factory contract for SessionFactory, lookup client, provider, per-attempt collector factory, parser, runtime config, clock and UUID factories. `handle_collection_dispatch` validates initial POLICY/null scope, performs initial lookup, then calls `load_bound_collection_attempt` before loading current Source config. `PERSISTED`/`FINALIZED` calls the command-locked `replay_staged_collection` immediately, and `INVALIDATED` raises a fixed authorization error. Only a missing attempt loads approved input and reserves; under the reservation Source lock, `reserve_collection_attempt` rechecks max DB policy revision before mode/counter mutation. A `RESERVED` attempt loads approved input and requires its stored effective revision to equal the current config/DB revision. It then obtains a command-scoped claim in a short transaction before constructing an execution.

Start a heartbeat coordinator with separate short-lived Sessions and interval at most one third of the lease; renewals use PostgreSQL time and the exact token through child fetch and the separate synchronous parent parser. A per-attempt adapter implements `_StaticCollector.fetch(request)` while delegating to `StaticScrapyCollector.fetch(request, is_cancelled=heartbeat_failed)`. Failed/invalidated heartbeat cancels and reaps active fetch; a parser result that returns after lease loss is discarded and its stale token cannot persist. This guarantees single-writer persistence, not exactly-once external work.

After parse, call `context.enter_stage(PERSIST, policy_revision=...)`, require fresh lookup and healthy heartbeat, then renew synchronously. Stop and join the heartbeat before `commit_collection_candidate` so no background renewal races its claim clear/PERSISTED transition. On known precommit failure, stop/join, close resources, then release only an exact still-owned token after confirmed cleanup. On process death or uncertain close, rely on DB-clock expiry. Durable outbox delivery and its lookup remain Task 7.

- [ ] **Step 4: Run focused runtime regressions**

Run Step 2. Expected: PASS, including old same-DB worker tests and lookup client security tests.

- [ ] **Step 5: Review diff ownership and prepare the optional execution-handler commit**

Apply the global commit guard. Only after explicit user approval and clean ownership, run:

```powershell
git add src/epick_engine/source_collection/source_runtime.py src/epick_engine/source_collection/source_runtime_store.py tests/unit/source_collection/test_source_runtime.py tests/integration/source_collection/test_collection_runtime_storage.py tests/unit/source_collection/test_worker.py tests/unit/source_collection/test_w1_lookup_client.py
git commit -m "feat: fresh lookup 기반 정적 수집 실행 연결"
```

---

### Task 7: Route Collection and Gate Messages Without Competing Consumers

**Files:**
- Modify: `src/epick_engine/source_collection/commit_gate_runtime.py`
- Modify: `src/epick_engine/source_collection/source_runtime.py`
- Create: `tests/unit/source_collection/test_source_runtime_router.py`
- Modify: `tests/unit/source_collection/test_commit_gate_runtime.py`
- Modify: `tests/integration/source_collection/test_commit_gate_delivery.py`

**Interfaces:**
- Consumes: authenticated `QueueDelivery`, strict JSON W1 dispatch/gate parsers, an injected Task 6 collection handler, and the Task 5 gate applier.
- Produces: `SourceRuntimeMode = Literal["mixed", "collection", "gate"]`, `consume_source_runtime_once(session_factory, queue, expected_sender_id, *, mode, collection_handler, gate_applier) -> ConsumeResult`, a lookup-gated staged relay hook, and a source-runtime queue protocol that can extend receipt visibility while work is active.

- [ ] **Step 1: Write failing routing and delivery tests**

For a shared physical queue, enqueue Core dispatch, direct-registration dispatch, PREPARE and FINALIZE and assert one `mode="mixed"` router dispatches by exact `message_type` without a second receiver. For dedicated queues, assert `mode="collection"` rejects gate messages without deletion and `mode="gate"` rejects collection messages without deletion. In both mixed and dedicated-gate topology, a valid FINALIZE must invoke `apply_collection_commit_gate` and promote the eligible pointer; the existing CT15 gate-only `consume_once` default remains private-only and is never used as the general runtime gate consumer.

Verify `System SenderId` before parsing untrusted JSON. Duplicate keys, non-finite numbers, oversized body, unknown type, wrong producer/scope/schema and sender mismatch must not open DB or invoke lookup. Delete receipt only after durable collection stage or durable gate ACK commit.

For staged-result relay, strict-parse the stored `StagedResultProposal.command`, reconstruct `LookupRequest(command_id, execution_fence, owner_deletion_epoch)`, call the lower-level lookup API because the original W1 wrapper/pin is not durably stored, and require AVAILABLE plus full returned command equality immediately before send. Non-AVAILABLE/lookup error means no send and no delivered timestamp. ACK relay remains governed by committed gate receipt and does not invent a collection lookup requirement. While collection work is active, extend receipt visibility from the configured lease/heartbeat boundary; test extension failure, redelivery and delete ordering rather than inheriting the CT15 adapter's fixed 60-second assumption.

- [ ] **Step 2: Run router tests and confirm RED**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/source_collection/test_source_runtime_router.py tests/unit/source_collection/test_commit_gate_runtime.py tests/integration/source_collection/test_commit_gate_delivery.py -q --tb=short
```

Expected: FAIL because mixed routing and injectable gate/send authorization are absent.

- [ ] **Step 3: Add compatible runtime injection points**

Keep existing defaults while adding a keyword-aware protocol and one send callback:

```python
class GateApplier(Protocol):
    def __call__(
        self,
        session: Session,
        gate_command: CommitGateCommand,
        *,
        ack_message_id: UUID,
        occurred_at: datetime,
    ) -> CommitGateAckProposal:
        raise NotImplementedError


BeforeSend = Callable[[str, Mapping[str, object]], None]
```

Extend the signatures to `consume_once(session_factory: SessionFactory, queue: Queue, expected_sender_id: str, *, clock: Callable[[], datetime] = _utc_now, message_id_factory: Callable[[], UUID] = uuid4, apply_gate: GateApplier = apply_commit_gate) -> ConsumeResult` and `relay_once(session_factory: SessionFactory, queue: Queue, *, clock: Callable[[], datetime] = _utc_now, command_id: UUID | None = None, before_send: BeforeSend | None = None) -> RelayResult`.

Adapt exact keyword calling in implementation rather than changing the public `apply_commit_gate` signature. `consume_source_runtime_once` requires explicit `mode` and keyword-only `collection_handler`; its general-runtime `gate_applier` defaults to `apply_collection_commit_gate`. `mixed` and `gate` always use that applier, while `collection` cannot dispatch a gate. The operator selects one mixed loop when physical queue identity is equal, or two dedicated loops with `collection` and `gate` modes when it differs. CT15 gate-only callers retain the existing `consume_once` default `apply_gate=apply_commit_gate`. The general relay callback validates only `private_staged_outbox` payloads by reconstructing lookup identity from the strict stored proposal command and comparing the returned full command.

- [ ] **Step 4: Implement the single mixed-queue dispatcher**

`consume_source_runtime_once` receives once, authenticates sender, strict-decodes once, inspects exact `message_type`, enforces the explicit mode allowlist, then calls either the injected collection handler or the injected collection-aware gate handler. Dependencies are never resolved from import-time globals. It never hands a failed parse to the other parser. Unsupported or wrong-mode messages remain undeleted and return a fixed safe status without raw body, receipt, URL, bearer, or DB DSN.

Run Step 2. Expected: PASS, including existing gate-only tests.

- [ ] **Step 5: Review diff ownership and prepare the optional routing commit**

Apply the global commit guard. Only after explicit user approval and clean ownership, run:

```powershell
git add src/epick_engine/source_collection/commit_gate_runtime.py src/epick_engine/source_collection/source_runtime.py tests/unit/source_collection/test_source_runtime_router.py tests/unit/source_collection/test_commit_gate_runtime.py tests/integration/source_collection/test_commit_gate_delivery.py
git commit -m "feat: 수집 명령과 commit gate 단일 라우팅"
```

---

### Task 8: Add Fail-Closed Operator, CLI and Image Recipe

**Files:**
- Create: `src/epick_engine/source_collection/source_runtime_operator.py`
- Create: `tests/unit/source_collection/test_source_runtime_operator.py`
- Create: `tests/contract/source_collection/test_source_runtime_build.py`
- Create: `contracts/w2-private/source-runtime.md`
- Create: `Dockerfile.source-runtime`
- Create: `compose.source-runtime.yaml`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: DB URL, runtime config file, W1 lookup endpoint/bearer/CA, inbound/outbound queue URLs, expected SenderId, existing `requirements.ct15.lock` hash-locked dependencies.
- Produces: `epick-w2-source-runtime preflight|consume-once|relay-once|run`.

- [ ] **Step 1: Write failing settings and preflight tests**

Require explicit values for:

```text
EPICK_DATABASE_URL
W2_SOURCE_RUNTIME_CONFIG_FILE
W1_LOOKUP_ENDPOINT
W1_LOOKUP_BEARER
W1_LOOKUP_CA_FILE
W1_COLLECTION_COMMAND_QUEUE_URL
W1_COMMIT_GATE_COMMAND_QUEUE_URL
W1_PRIVATE_INBOUND_QUEUE_URL
W1_EXPECTED_SYSTEM_SENDER_ID
```

Compose additionally requires `W2_SOURCE_RUNTIME_CONFIG_HOST_FILE` and `W1_LOOKUP_CA_HOST_FILE` as host-side interpolation variables only; the application settings parser does not consume them. The container-facing values remain fixed at `/run/epick/source-runtime/config.json` and `/run/epick/source-runtime/w1-ca.pem`; never pass a Windows or arbitrary host path as the in-container value.

Test both topologies: same collection/gate queue means one mixed consumer; different URLs mean dedicated consumers. Reject partial equality, HTTP endpoint, unverified/missing CA, empty bearer/sender, non-PostgreSQL DB, unencrypted queue, queue without DLQ, unknown migration head, config file writable by group/everyone where Windows ACL evidence is available, and config missing a Source entry. `repr(settings)` and all errors must redact bearer, DSN, receipt and full endpoint query.

Derive and validate one canonical AWS region from all three HTTPS QueueUrls, then compare physical queues by canonical QueueArn/normalized metadata identity rather than raw URL text. Only collection-command == commit-gate-command may select a shared mixed input; the W1 private inbound queue must be physically distinct from both inputs so the runtime cannot consume its own staged result or ACK.

- [ ] **Step 2: Run operator tests and confirm RED**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/source_collection/test_source_runtime_operator.py -q --tb=short
```

Expected: FAIL because operator/settings/CLI do not exist.

- [ ] **Step 3: Implement bounded commands and preflight**

Implement:

```text
preflight      validate config, migration head, DB connectivity and queue metadata; consume/send/delete 0회
consume-once   receive at most one authenticated inbound message
relay-once     send at most one durable staged-result or ACK record
run            alternate bounded consume/relay calls, stop on signal after current delivery
```

`run` must not create application-level retry loops for lookup 429/503 or collector failures. Queue redelivery remains the transport behavior. Emit only fixed status codes/counts; never emit payloads or secrets.

When collection and gate URLs are equal, `run` starts exactly one `mode="mixed"` consumer. When they differ, it starts one `mode="collection"` consumer and one `mode="gate"` consumer; the latter is explicitly wired to `apply_collection_commit_gate`. No topology may route general-runtime gate messages through the legacy private-only default.

Add `epick-w2-source-runtime = "epick_engine.source_collection.source_runtime_operator:main"` to `[project.scripts]` for local use. The image uses `PYTHONPATH=/app/src` and `python -m epick_engine.source_collection.source_runtime_operator`, so it does not depend on package metadata excluded by `.dockerignore`. Reuse the already hash-locked `requirements.ct15.lock`; do not add a second dependency set or a new library. Construct the injected Task 6 handler and a source-runtime-specific queue adapter here, including lease-aware receipt visibility extension; do not blindly reuse the CT15 fixed-60-second adapter.

- [ ] **Step 4: Add non-root immutable image and disabled compose profile**

`Dockerfile.source-runtime` must require digest-pinned Python 3.12 image and 40-hex `SOURCE_SHA`, install with `--require-hashes --no-deps`, copy only runtime source/migrations/Alembic metadata available through the current `.dockerignore`, set `PYTHONPATH=/app/src`, use the module entrypoint, run as UID/GID 10001, and default to `preflight`. Runtime config and CA are bind-mounted files; contracts or `pyproject.toml` are not required in the image.

`compose.source-runtime.yaml` must use profile `source-runtime`, container `read_only`, `cap_drop: [ALL]`, `no-new-privileges`, bounded tmpfs, no embedded secrets, and `${VAR:?message}` for every required external value. It must use long-form bind mounts (`type: bind`, required host `source`, fixed container `target`, `read_only: true`) for config and CA so Windows drive-letter colons cannot corrupt short syntax. Set the two container-facing env values to `/run/epick/source-runtime/config.json` and `/run/epick/source-runtime/w1-ca.pem`; do not create PostgreSQL, queues, IAM, registry, or public networks.

Add `test_source_runtime_build.py` to read both tracked recipes and assert the digest regex checks, 40-hex source revision check, hash-locked install, non-root UID/GID and module entrypoint, compose profile/container read-only/cap-drop/no-new-privileges/tmpfs, both required host-source variables, fixed container destinations, long-form read-only file mounts, and every required `${VAR:?message}` reference. Assert no literal bearer, DSN, account ID, role ARN or queue URL appears. This static contract is local evidence only; it does not replace actual host-path resolution, image build, registry scan or deployment.

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/source_collection/test_source_runtime_operator.py -q --tb=short
.venv\Scripts\python.exe -m pytest tests/contract/source_collection/test_source_runtime_build.py -q --tb=short
.venv\Scripts\python.exe -m build
```

Expected: PASS. Do not build/push an image without separately approved immutable base image and registry.

- [ ] **Step 5: Review diff ownership and prepare the optional operator/build commit**

Apply the global commit guard. Only after explicit user approval and clean ownership, run:

```powershell
git add src/epick_engine/source_collection/source_runtime_operator.py tests/unit/source_collection/test_source_runtime_operator.py tests/contract/source_collection/test_source_runtime_build.py contracts/w2-private/source-runtime.md Dockerfile.source-runtime compose.source-runtime.yaml pyproject.toml
git commit -m "feat: 일반 수집 runtime 실행 경계 추가"
```

---

### Task 9: Run Full Verification and Synchronize Evidence

**Files:**
- Modify: `../../specs/001-official-source-collection/validation.md`
- Modify: `../../specs/001-official-source-collection/tasks.md`
- Modify: `../../specs/001-official-source-collection/quickstart.md`
- Modify: `contracts/w2-private/source-runtime.md`

**Interfaces:**
- Consumes: all Tasks 1~8 and approved local PostgreSQL only.
- Produces: reproducible evidence with local/real/external Gate distinctions.

- [ ] **Step 1: Run focused tests by boundary**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/source_collection/test_source_runtime_input.py tests/unit/source_collection/test_source_runtime.py tests/unit/source_collection/test_source_runtime_router.py tests/unit/source_collection/test_source_runtime_operator.py -q --tb=short
.venv\Scripts\python.exe -m pytest tests/integration/source_collection/test_collection_runtime_storage.py tests/integration/source_collection/test_collection_finalize_pointer.py tests/integration/source_collection/test_private_commit_gate.py tests/integration/source_collection/test_commit_gate_delivery.py tests/integration/source_collection/test_atomic_persistence.py -q --tb=short
.venv\Scripts\python.exe -m pytest tests/contract/source_collection/test_w1_transport.py tests/contract/source_collection/test_commit_gate_contracts.py tests/contract/source_collection/test_runtime_contracts.py tests/contract/source_collection/test_source_runtime_build.py tests/contract/source_collection/test_source_policy_writer_contract.py -q --tb=short
```

Expected: all focused tests PASS with an explicitly approved isolated PostgreSQL DSN. Record exact counts and duration from fresh output.

- [ ] **Step 2: Run full quality gates**

```powershell
.venv\Scripts\python.exe -m pytest -q --tb=no
.venv\Scripts\python.exe -m ruff check src tests migrations scripts
.venv\Scripts\python.exe -m ruff format --check src tests migrations scripts
.venv\Scripts\python.exe -m mypy src
git diff --check
```

Expected: new tests and all existing applicable tests PASS. If the known T067/RenderedCollector/restriction failures remain, record exact unchanged node IDs and do not report the full suite green.

- [ ] **Step 3: Run migration and package checks**

Verify isolated `upgrade 0007_restriction_receipt -> head`, head stamp, SQLAlchemy metadata parity, unsupported destructive downgrade response, wheel/sdist build, console entrypoint `--help`, and `preflight` failure with every required setting removed one at a time.

- [ ] **Step 4: Update only evidence-backed status**

In `validation.md`, record commands, exact pass/fail/skip counts, approved DB boundary, no-live-network statement, and independent review findings. Mark T099 complete only if Tasks 1~8 and all in-scope checks pass. Keep T089, T091, T067, W1 non-policy resume, actual registry/IAM/queue/HTTPS and joint CT15 open.

- [ ] **Step 5: Review diff ownership and prepare the optional evidence commit**

Apply the global commit guard. Only after explicit user approval and clean ownership, run:

```powershell
git add contracts/w2-private/source-runtime.md docs/superpowers/plans/2026-09-20-w2-finalize-pointer-runtime.md
git commit -m "docs: 수집 runtime 검증 증거 반영"
```

The `specs/001-official-source-collection` files live outside the Engine Git root. Update them in the shared workspace and verify their links, but do not attempt to stage them from the Engine repository.

Do not push, deploy, create queues, mutate IAM, contact live Source pages, or run joint CT15 without separate authorization and supplied environment values.

---

## Self-Review Record

- **Spec coverage:** approved observation ordering, atomic public/private commit, policy SSOT, stage kind, FINALIZE-only promotion, failure observation, purge/replay, input fail-closed, queue topology, CLI/build and external Gate separation are each mapped to Tasks 1~9.
- **Placeholder scan:** no unresolved implementation marker remains; external W1 resume and deployment inputs are explicit out-of-scope Gates rather than implementation placeholders.
- **Type consistency:** `W1Dispatch`, `CollectionRuntimeAttempt`, `StaticCollectionInput`, `PreparedCollectionCommit`, `StagedResultProposal`, `CommitGateCommand` and `CommitGateAckProposal` names match current code and are introduced before downstream use.
- **Review Focus coverage:** the six listed conflict/atomicity/order/replay/authorization/writer-transition classes have explicit tests in Tasks 1, 2, 4, 5, 6, 7 and 8.
- **Independent review:** replay/gate locking, policy-writer serialization, claim-token commit binding, topology wiring, invalidation cleanup, compatibility alias ripple and parser-heartbeat limits were rechecked; no actionable P0/P1/P2 finding remains. Graph generation/coverage was unavailable, so the review used bounded source fallback and records that limitation.
- **Residual trade-off:** the claim guarantees DB single-writer persistence. Because the current parent parser is not cooperatively cancellable, lease loss may briefly overlap read-only work; stale results cannot persist and exactly-once external execution is not claimed.
- **Constitution check:** no new external service or dependency, no inferred permission, no private field in public outbox, no W1 state ownership duplication, and no unverified deployment claim is introduced.
