# W2 Private Deletion Scope v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace incomplete W1-supplied deletion ID lists with W2-owned, transactionally complete account/Project deletion while preserving public Source history.

**Architecture:** A new private v2 command names a scope, not rows. W2 persists explicit scope attribution and tombstones, serializes every private write and deletion on the owner row, and calls W1 scope purge only after its DB commit. Unclassified legacy rows block Project deletion; W1 must serialize owner deletion epochs until purge and ACK complete.

**Tech Stack:** Python 3.12, Pydantic/JSON Schema, SQLAlchemy 2, Alembic, PostgreSQL, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-23-w2-private-deletion-scope-v2-design.md`

## Global Constraints

- Keep v1 command/ACK schemas and historical receipts readable, but never accept v1 on the new production deletion seam.
- Command epoch is an integer in `1..9223372036854775807`; scope and UUIDs are canonical, and W1 outer owner/target/scope must match the payload.
- W2 cannot infer account scope from a missing `project_ref` or Project scope from `accepted_resource_ref`; W1 must provide an authenticated explicit scope proof for new private writes.
- A Project request encountering any owner-private parent row with unproven scope rolls back without receipt, epoch advance, purge, or ACK.
- Account deletion removes all owner-private collection payloads; both scopes preserve shared public Source/Version/Evidence/observation/outbox history.
- All private writes and deletions take the owner-state lock before other mutable locks; a tombstoned owner/Project or stale epoch cannot acquire new private state.
- W2 DB commit precedes W1 scope purge and ACK. W1 must finish purge/ACK before advancing that owner's deletion epoch; stale replay does neither.
- No real owner data, secrets, queue URLs, or DB credentials in fixtures, logs, commits, or handoff documents. G-04/G-07 controls production tombstone retention.
- Existing full-suite `RenderedCollector` failures are outside this plan. Do not mark T050/T058 or W1–W2 READY from local v2 tests.

## Review Focus

1. An owner has one legacy unclassified dedup or runtime row while another Project is deleted: `test_v2_project_deletion_rolls_back_on_any_unclassified_owner_row` must show zero mutations.
2. A stage/reservation races with Project deletion: `test_v2_deletion_serializes_late_private_writers` must prove writer-first rows are deleted and deletion-first writers reject.
3. Same deletion ID with altered scope or old v1 receipt: `test_v2_receipt_rejects_changed_scope_and_v1_reuse` must reject without interpreting v1 as v2.
4. W1 purge raises after W2 commit, then process restarts: `test_v2_purge_failure_retries_same_receipt_after_restart` must repeat scope purge and ACK only on the current epoch.
5. Two owners share public Source history: `test_v2_account_deletion_preserves_other_owner_and_public_history` must keep public IDs and the other owner's private rows unchanged.

---

### Task 1: Versioned v2 command and ACK contracts

**Files:**
- Create: `contracts/w2-private/private-deletion-command-v2.schema.json`
- Create: `contracts/w2-private/private-deletion-ack-v2.schema.json`
- Create: `src/epick_engine/source_collection/private_deletion_v2.py`
- Create: `tests/contract/source_collection/test_private_deletion_v2_contracts.py`
- Create: synthetic JSON fixtures under `tests/fixtures/w2_private_deletion_v2/`

**Interfaces:**
- Produces: `PrivateDeletionScope(kind: Literal["ACCOUNT", "PROJECT"], project_id: UUID | None)`, `PrivateDeletionCommandV2(deletion_id, owner_user_id, deletion_epoch, scope)`, `PrivateDeletionAckV2(deletion_id, owner_user_id, deletion_epoch, scope, outcome)` and `command_digest_v2(command) -> str`.
- Consumes: the existing v1 UUID/epoch rules in `worker.py`; does not modify v1 classes or schema files.

- [ ] **Step 1: Write contract RED tests.** Validate both scope shapes, canonical UUIDs, bool/zero/overflow epochs, extra keys, changed-scope same-ID data, ACK scope echo, and v1 rejection at `PrivateDeletionCommandV2.from_mapping`.

```python
assert PrivateDeletionCommandV2.from_mapping({
    "schema_version": "w2.private-deletion.v2", "deletion_id": str(DELETION_ID),
    "owner_user_id": str(OWNER_ID), "deletion_epoch": 7,
    "scope": {"type": "PROJECT", "project_id": str(PROJECT_ID)},
}).scope.project_id == PROJECT_ID
with pytest.raises(WorkerContractViolation):
    PrivateDeletionCommandV2.from_mapping({**valid_v2, "attempt_ids": []})
```

- [ ] **Step 2: Run** `python -m pytest tests/contract/source_collection/test_private_deletion_v2_contracts.py -q`; expect failure because v2 contracts do not exist.
- [ ] **Step 3: Add exact-key v2 parsing and two draft-2020-12 schemas.** Use the same canonical UUID regex and signed-64-bit maximum as v1; JSON Schema `oneOf` makes ACCOUNT contain only `type` and PROJECT require `project_id`. Digest canonical JSON with sorted keys and compact separators, including `schema_version` and scope.

```python
@dataclass(frozen=True, slots=True)
class PrivateDeletionScope:
    kind: Literal["ACCOUNT", "PROJECT"]
    project_id: UUID | None

def command_digest_v2(command: PrivateDeletionCommandV2) -> str:
    return hashlib.sha256(json.dumps(command.to_mapping(), sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run** the Task 1 contract tests, Ruff on the new Python files, and `git diff --check`; require exit 0.
- [ ] **Step 5: Commit** only Task 1 files with a Korean conventional subject such as `feat(w2): 삭제 범위 v2 계약 추가`.

### Task 2: Migration, private inventory, and explicit attribution

**Files:**
- Create: `migrations/versions/0010_private_deletion_scope_v2.py`
- Modify: `src/epick_engine/source_collection/persistence.py` (`CollectionAttempt`, `CollectionRuntimeAttempt`, `RequestDeduplication`, `PrivateDeletionOwnerState`, `PrivateDeletionReceipt`)
- Modify: `src/epick_engine/source_collection/commit_gate_store.py` (`PrivateCommitStage`)
- Create: `src/epick_engine/source_collection/private_scope.py`
- Modify: `tests/unit/source_collection/test_alembic_config.py`
- Create: `tests/integration/source_collection/test_private_deletion_scope_storage.py`

**Interfaces:**
- Produces: `PrivateWriteScope(owner_user_id, owner_deletion_epoch, kind, project_id, authority_ref, command_id=None, job_id=None)`, `lock_private_write_scope(session, proof) -> None`, and `ScopeUnclassified`/`PrivateScopeRejected` errors. Write epoch permits `0..9223372036854775807`; deletion commands remain strictly positive.
- Consumes: Task 1 `PrivateDeletionScope`; Task 3 passes a W1-authenticated proof to every new private writer.

- [ ] **Step 1: Add failing migration tests.** On an isolated approved PostgreSQL schema, upgrade `0009` to `0010_private_deletion_scope_v2`, inspect attribution columns/constraints, verify `collection_attempts.owner_deletion_epoch` is bigint, and verify an old receipt is tagged v1. Assert `scripts.get_heads()` equals the new head.
- [ ] **Step 2: Run** `python -m pytest tests/unit/source_collection/test_alembic_config.py tests/integration/source_collection/test_private_deletion_scope_storage.py -q`; expect new-head/column failures.
- [ ] **Step 3: Add the migration and mapped columns.** Private parent rows get `private_scope_kind IN ('UNKNOWN','ACCOUNT','PROJECT')` and nullable `project_id`. The DB constraint requires PROJECT to have a Project ID and ACCOUNT to have none; UNKNOWN permits either because legacy `CollectionAttempt.project_id` may already be set without a separate authorization proof. All pre-migration private parents remain UNKNOWN; a separate verified backfill may classify them later. Add `account_deleted` to owner state, a `(owner_user_id, project_id)` Project tombstone table, and receipt `contract_version` default/backfilled to v1. Add owner/scope indexes. The existing `0009` revision remains unchanged.

```python
op.add_column("request_deduplications", sa.Column("private_scope_kind", sa.String(16),
    nullable=False, server_default="UNKNOWN"))
op.add_column("request_deduplications", sa.Column("project_id", postgresql.UUID(as_uuid=True)))
op.add_column("private_deletion_receipts", sa.Column("contract_version", sa.String(32),
    nullable=False, server_default="w2.private-deletion.v1"))
```

- [ ] **Step 4: Implement proof validation and owner-first lock.** A proof is constructed only by a trusted W1 adapter; validate its non-empty authority reference, exact owner/epoch binding, command/job binding where those identities exist, and explicit ACCOUNT/PROJECT shape. `lock_private_write_scope` creates/locks the owner row, rejects account/Project tombstones and `proof.owner_deletion_epoch < latest_epoch`, and rejects write epochs outside nonnegative signed 64-bit. No absent proof silently becomes ACCOUNT.
- [ ] **Step 5: Run** the migration/storage tests and `git diff --check`; require exit 0. Record that the privacy gate still governs tombstone retention.
- [ ] **Step 6: Commit** Task 2 files with a Korean conventional subject.

### Task 3: Fence every W2-private write path

**Files:**
- Modify: `src/epick_engine/source_collection/persistence.py` (`resolve_request_deduplication`, `commit_prepared_collection`, legacy `stage_private_result`)
- Modify: `src/epick_engine/source_collection/commit_gate_store.py` (`stage_private_result`, `apply_commit_gate`)
- Modify: `src/epick_engine/source_collection/source_runtime_store.py` (`reserve_collection_attempt`, claim/replay paths)
- Modify: `src/epick_engine/source_collection/source_runtime.py`, `commit_gate_operator.py` (trusted scope-proof injection; fail closed when absent)
- Update direct-call test helpers and fixtures in `tests/integration/source_collection/` and focused operator unit tests; do not rewrite unrelated assertions.

**Interfaces:**
- Consumes: Task 2 `PrivateWriteScope` and `lock_private_write_scope`; proof binds the exact command owner/job/epoch and PROJECT ID.
- Produces: correctly attributed new `CollectionAttempt`, `RequestDeduplication`, `CollectionRuntimeAttempt`, and `PrivateCommitStage`; descendants inherit the parent scope.

- [ ] **Step 1: Write failing tests** for missing/mismatched proof, explicit ACCOUNT and PROJECT persistence, stale epoch, tombstoned account/Project, and writer-first/deletion-first concurrency. Include `stage_private_result`, `apply_commit_gate` (including missing-stage PURGE), runtime reservation/claim, dedup creation, and legacy commit/replay.
- [ ] **Step 2: Run** the focused new write-fence tests with approved PostgreSQL; expect missing-proof/tombstone failures.
- [ ] **Step 3: Thread the proof into every write transaction before existing stage/source locks.** Where W1 already supplies an `ExecutionAuthorityGrant`, extend that trusted grant with explicit scope; other W1-adopted entry points require a trusted proof parameter/provider. Validate binding before setting `private_scope_kind`/`project_id`; reject absence in production entry points. Preserve the existing public-commit and operation-local PURGE semantics.

```python
with session.begin():
    lock_private_write_scope(session, proof)
    # Existing stage/source lock and private mutation follow only after the fence.
```

- [ ] **Step 4: Run** affected integration files, operator unit tests, Ruff, and mypy; then repair only direct callers impacted by the new required proof. No test may treat a null `project_ref` as sufficient account proof.
- [ ] **Step 5: Commit** Task 3 files with a Korean conventional subject.

### Task 4: Atomic scope deletion and v2 consumer recovery

**Files:**
- Modify: `src/epick_engine/source_collection/persistence.py` (new `apply_private_deletion_v2`)
- Modify: `src/epick_engine/source_collection/worker.py` or `private_deletion_v2.py` (new `process_private_deletion_v2` and scope-side-effect protocol)
- Create: `tests/integration/source_collection/test_private_deletion_scope_v2.py`
- Modify: `tests/contract/source_collection/test_private_deletion_v2_contracts.py`

**Interfaces:**
- Consumes: Tasks 1–3 command, receipt version, explicit attribution, and owner lock.
- Produces: `apply_private_deletion_v2(session, command) -> Literal['APPLIED','DUPLICATE','STALE']`; `process_private_deletion_v2(session_factory, command, side_effects) -> PrivateDeletionAckV2 | None`, returning `None` for stale commands. The side-effects protocol exposes `purge_private_scope(owner_user_id, scope)` and `acknowledge(deletion_id, deletion_epoch)`.

- [ ] **Step 1: Add RED approved-PostgreSQL tests** matching all five Review Focus cases, plus foreign-owner isolation, Project A/B separation, schema-version collision, signed64 max, same-epoch conflict, and FK-safe stage descendant removal.
- [ ] **Step 2: Run** `python -m pytest tests/integration/source_collection/test_private_deletion_scope_v2.py -q`; expect v2 API failures.
- [ ] **Step 3: Implement owner-locked scope deletion.** Check `deletion_id` receipt digest and contract version first; old same-ID receipt after a newer epoch is STALE, same-ID changed body conflicts. For Project scope, scan all four owner-private parent tables and reject UNKNOWN before deleting any row. Delete private child tables in FK order, then matching parents, persist account/Project tombstone and v2 receipt in one transaction. Account scope deletes all owner-private parent rows. Keep public tables untouched.

```python
with session_factory.begin() as session:
    outcome = apply_private_deletion_v2(session, command)
if outcome == "STALE":
    return None  # Never publish a completion ACK for a stale command.
side_effects.purge_private_scope(owner_user_id=command.owner_user_id, scope=command.scope)
side_effects.acknowledge(deletion_id=command.deletion_id,
    deletion_epoch=command.deletion_epoch)
return PrivateDeletionAckV2.from_command(command, outcome=outcome)
```

- [ ] **Step 4: Prove failure/restart semantics.** Purge exceptions leave a committed receipt and no ACK; replay of the exact current command is DUPLICATE and retries purge; after a newer completed epoch an old replay is STALE and does neither. W1, not W2, prevents new owner epochs before prior purge/ACK.
- [ ] **Step 5: Run** the v2 contract/integration tests, the existing T067 tests, Ruff, mypy, and `git diff --check`; require no new failure.
- [ ] **Step 6: Commit** Task 4 files with a Korean conventional subject.

### Task 5: Operator head, complete ripple checks, and W1 handoff

**Files:**
- Modify: `src/epick_engine/source_collection/source_runtime_operator.py`, `commit_gate_operator.py`
- Modify: `contracts/w2-private/ct15-runtime.md`
- Update 0009-head assertions in `tests/unit/source_collection/test_source_runtime_operator.py`, `test_commit_gate_operator.py`, `test_alembic_config.py`, and integration migration tests that assert latest head; preserve historical 0009 upgrade coverage.
- Create: `../.agents/docs/W2_W1_Private_Deletion_Scope_V2_Handoff_2026-09-23.md` under the project workspace root (outside the Engine Git repository), or use the user's requested handoff path if changed before execution.

**Interfaces:**
- Consumes: Tasks 1–4 final v2 schemas and migration.
- Produces: preflight requires exactly one `0010_private_deletion_scope_v2` DB head before queue metadata; W1 receives exact schema paths/hashes, W2 full SHA, proof/outer-envelope obligations, tests and limits.

- [ ] **Step 1: Add failing operator tests** for 0009/unknown/multiple/duplicate heads and prove rejection before any SQS metadata call; update migration-chain tests for new head.
- [ ] **Step 2: Run** focused operator/migration tests and observe the new-head failures.
- [ ] **Step 3: Change exact-head constants and CT15 runbook.** Enumerate all exact `0009_private_deletion_receipt` references; change only current-head expectations to 0010. Preserve the old-revision migration test and old CT15 run evidence as historical facts.
- [ ] **Step 4: Run** focused approved-PostgreSQL v2 tests and all directly affected tests; then full `python -m pytest -q`, `python -m ruff check src tests`, `python -m ruff format --check src tests`, `python -m mypy src`, and `git diff --check`. Report any pre-existing `RenderedCollector` failures separately and do not claim a green full suite unless it is green.
- [ ] **Step 5: Record the actual W2 full SHA and contract hashes in the handoff after the final commit.** State that W1 must add the W2 target/migration, authenticated explicit scope proof on collection and commit-gate writes, v2 outer envelope/dispatcher/ACK, scope-based W1 purge, and per-owner epoch serialization. Do not share credentials or claim real AWS/SQS E2E.
- [ ] **Step 6: Commit** code/docs with a Korean conventional subject; verify clean local status. Do not push, deploy, or tear down shared resources without the user's explicit direction.

## Execution handoff

Implement Tasks 1–5 in order because the scope representation and migration are prerequisites for the write fence and deletion consumer. A fresh reviewer should check each task's cross-boundary invariants before the next task proceeds. The W1 repository is outside this plan's write ownership; W1 receives an explicit contract handoff after W2 local verification.
