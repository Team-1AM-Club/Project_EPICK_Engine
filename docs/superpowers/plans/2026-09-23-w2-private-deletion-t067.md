# W2 Private Deletion (T067) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** W1이 승인한 계정·프로젝트 범위 private-deletion 명령을 W2가 안전하게 소비하여 owner 전용 수집 상태를 삭제하고 monotonic epoch·재시도로부터 public history를 보호한다.

**Architecture:** W2는 versioned command/ACK JSON Schema와 Python consumer port를 제공한다. 소비자는 PostgreSQL transaction에서 owner별 deletion epoch를 잠그고 owner-private attempt·deduplication을 삭제한 뒤 immutable receipt와 함께 commit한다. 이후 W1 private-reference purge가 성공하면 ACK port를 호출한다. W1은 authenticated authorization, outer envelope, transport dispatch/retry와 공동 E2E를 계속 소유한다.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, Alembic, PostgreSQL, pytest, jsonschema Draft 2020-12.

**Spec:** docs/superpowers/specs/2026-09-23-w2-private-deletion-t067-design.md

## Global Constraints

- W2는 w2.private-deletion.v1 command와 w2.private-deletion-ack.v1 ACK payload만 소유하며 W1 outer envelope는 수정하지 않는다.
- 명령에는 public Source, SourceVersion, Evidence, retained body, public event 식별자나 본문을 넣지 않는다.
- 삭제 대상은 command owner의 명시된 private attempt/deduplication/reference scope뿐이며 다른 owner와 모든 public history를 보존한다.
- 동일 deletion_id 재전달은 안전해야 하고 이전 deletion_epoch는 delete·purge·ACK를 수행하지 않는다.
- private-reference purge 실패 시 이미 commit된 삭제·receipt를 유지하고 transport ACK는 발생시키지 않는다. 같은 command 재전달은 purge를 재시도한다.
- 기존 operation-local commit-gate PURGE를 account/project private deletion에 사용하지 않는다.
- production head는 forward-only Alembic 0009_private_deletion_receipt이며 CT15 preflight와 W1 handoff는 이를 명시한다.

## Review Focus

- 다른 owner UUID가 들어오면 rollback하고 아무 callback도 호출하지 않는다.
- 동일 deletion_id의 다른 command 내용은 stored receipt를 재사용하지 않고 no-ACK 오류가 된다.
- 낮은 epoch는 private-reference purge와 ACK도 수행하지 않는다.
- purge callback 예외는 ACK를 막으며, 동일 command 재전달이 안전하게 purge를 재시도한다.
- 0008 DB를 0009로 upgrade한 뒤 CT15는 새 단일 head만 허용한다.

---

## File Structure

| File | Responsibility |
| --- | --- |
| contracts/w2-private/private-deletion-command.schema.json | W1→W2 payload structural validation과 public-field 금지 |
| contracts/w2-private/private-deletion-ack.schema.json | W2→W1 ACK discriminator/outcome |
| tests/fixtures/w2_private_deletion/ | valid/invalid command·ACK fixture |
| tests/contract/source_collection/test_private_deletion_contracts.py | schema와 Python command validation regression |
| src/epick_engine/source_collection/persistence.py | owner epoch state, PrivateDeletionReceipt와 owner-scoped delete helper |
| migrations/versions/0009_private_deletion_receipt.py | durable receipt forward migration |
| tests/integration/source_collection/test_private_deletion.py | existing RED scope/failure/race/replay test와 receipt conflict |
| src/epick_engine/source_collection/worker.py | command/ACK value object, side-effect protocol, transactional consumer |
| src/epick_engine/source_collection/source_runtime_operator.py | runtime migration head pin |
| src/epick_engine/source_collection/commit_gate_operator.py | CT15 preflight head pin |
| contracts/w2-private/ct15-runtime.md | W1 handoff contract and verification commands |

### Task 1: Versioned private-deletion contract and deterministic command validation

**Files:**
- Create: contracts/w2-private/private-deletion-command.schema.json
- Create: contracts/w2-private/private-deletion-ack.schema.json
- Create: tests/fixtures/w2_private_deletion/valid-command.json
- Create: tests/fixtures/w2_private_deletion/valid-ack-applied.json
- Create: tests/fixtures/w2_private_deletion/invalid-zero-epoch.json
- Create: tests/fixtures/w2_private_deletion/invalid-public-reference.json
- Create: tests/contract/source_collection/test_private_deletion_contracts.py
- Modify: src/epick_engine/source_collection/worker.py (public command/ACK definitions)

**Interfaces:**
- Produces: PrivateDeletionCommand(deletion_id: UUID, owner_user_id: UUID, deletion_epoch: int, attempt_ids: frozenset[UUID], request_deduplication_ids: frozenset[UUID], private_reference_keys: frozenset[str]).
- Produces: PrivateDeletionAcknowledgement(deletion_id: UUID, owner_user_id: UUID, deletion_epoch: int, outcome: Literal[APPLIED, DUPLICATE, STALE]).
- Consumes: authenticated W1 payload only; no W1 envelope or queue dependency.

- [ ] **Step 1: Write the failing contract tests**

    def test_private_deletion_command_fixture_validates_without_coercion() -> None:
        raw = _load("valid-command.json")
        _validator("private-deletion-command.schema.json").validate(raw)
        command = PrivateDeletionCommand.from_mapping(raw)
        assert command.deletion_epoch == 7
        assert command.attempt_ids == frozenset({UUID(raw["attempt_ids"][0])})

    @pytest.mark.parametrize("fixture", ["invalid-zero-epoch.json", "invalid-public-reference.json"])
    def test_private_deletion_rejects_invalid_or_public_scope(fixture: str) -> None:
        raw = _load(fixture)
        assert list(_validator("private-deletion-command.schema.json").iter_errors(raw))
        with pytest.raises(WorkerContractViolation):
            PrivateDeletionCommand.from_mapping(raw)

- [ ] **Step 2: Run test to verify it fails**

Run: python -m pytest tests/contract/source_collection/test_private_deletion_contracts.py -q

Expected: FAIL because schemas, fixtures, and PrivateDeletionCommand codec do not exist.

- [ ] **Step 3: Write minimal contract implementation**

    @dataclass(frozen=True)
    class PrivateDeletionCommand:
        deletion_id: UUID
        owner_user_id: UUID
        deletion_epoch: int
        attempt_ids: frozenset[UUID]
        request_deduplication_ids: frozenset[UUID]
        private_reference_keys: frozenset[str]

        @classmethod
        def from_mapping(cls, raw: Mapping[str, object]) -> Self:
            if raw.get("schema_version") != "w2.private-deletion.v1":
                raise WorkerContractViolation("private deletion schema version is invalid")
            # Require UUID/int/string values without lexical coercion and reject unknown keys.

Define schema_version w2.private-deletion.v1 and w2.private-deletion-ack.v1, additionalProperties false, UUID format, integer deletion_epoch >= 1, unique arrays. The command permits only the six private identifiers plus schema_version: no source, version, evidence, body, or public-event property.

- [ ] **Step 4: Run test to verify it passes**

Run: python -m pytest tests/contract/source_collection/test_private_deletion_contracts.py -q

Expected: PASS; valid payload round-trips and each invalid fixture fails both schema and Python validation.

- [ ] **Step 5: Commit**

    git add contracts/w2-private/private-deletion-command.schema.json contracts/w2-private/private-deletion-ack.schema.json tests/fixtures/w2_private_deletion tests/contract/source_collection/test_private_deletion_contracts.py src/epick_engine/source_collection/worker.py
    git commit -m "feat(w2): private 삭제 계약 추가"

### Task 2: Durable owner epoch and deletion receipt persistence

**Files:**
- Modify: src/epick_engine/source_collection/persistence.py (Base model and owner-scoped deletion helpers)
- Create: migrations/versions/0009_private_deletion_receipt.py
- Modify: tests/integration/source_collection/test_private_deletion.py
- Modify: tests/unit/source_collection/test_alembic_config.py

**Interfaces:**
- Produces: PrivateDeletionOwnerState(owner_user_id, latest_epoch) and PrivateDeletionReceipt(deletion_id, owner_user_id, deletion_epoch, command_digest, outcome, created_at).
- Produces: apply_private_deletion(session: Session, command: PrivateDeletionCommand) -> Literal[APPLIED, DUPLICATE, STALE].
- Consumes: CollectionAttempt, RequestDeduplication, and Task 1 command type. Import that type only under TYPE_CHECKING inside persistence.py to avoid worker↔persistence runtime imports.

- [ ] **Step 1: Write failing durable-state tests**

    def test_same_deletion_id_with_different_private_scope_is_rejected(session_factory) -> None:
        _apply(session_factory, deletion_id=DELETE_ID, epoch=7, attempt_ids=frozenset({A1}))
        with pytest.raises(PersistenceConflict, match="deletion receipt does not match command"):
            _apply(session_factory, deletion_id=DELETE_ID, epoch=7, attempt_ids=frozenset({A2}))

    def test_private_deletion_receipt_is_owner_scoped_and_monotonic(session_factory) -> None:
        assert _apply(session_factory, deletion_id=FIRST, epoch=7).outcome == "APPLIED"
        assert _apply(session_factory, deletion_id=LATE, epoch=6).outcome == "STALE"

- [ ] **Step 2: Run test to verify it fails**

Run: python -m pytest tests/integration/source_collection/test_private_deletion.py -q

Expected: FAIL because no receipt table/model or owner epoch lock exists.

- [ ] **Step 3: Write minimal persistence and migration**

    class PrivateDeletionOwnerState(Base):
        __tablename__ = "private_deletion_owner_states"
        owner_user_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
        latest_epoch: Mapped[int] = mapped_column(Integer, nullable=False)

    class PrivateDeletionReceipt(Base):
        __tablename__ = "private_deletion_receipts"
        __table_args__ = (
            UniqueConstraint("owner_user_id", "deletion_epoch", name="uq_private_deletion_receipts_owner_epoch"),
            CheckConstraint("deletion_epoch > 0", name="positive_deletion_epoch"),
        )
        deletion_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
        owner_user_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
        deletion_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
        command_digest: Mapped[str] = mapped_column(String(64), nullable=False)
        outcome: Mapped[str] = mapped_column(String(16), nullable=False)

Create the owner state row with INSERT ON CONFLICT DO NOTHING, then lock that row with SELECT FOR UPDATE. This serializes even concurrent first deletions when no receipt existed. A duplicate deletion_id must have the same command digest; lower epoch returns STALE. Validate every existing candidate CollectionAttempt and RequestDeduplication with both primary-key membership and owner_user_id before deleting; already-absent IDs in a replay do not cause conflict. Insert APPLIED receipt, advance latest_epoch, and delete only validated private rows in the same transaction; never query/delete public tables. Revision 0009_private_deletion_receipt revises 0008_collection_runtime and has the established forward-only downgrade RuntimeError.

- [ ] **Step 4: Run test to verify it passes**

Run: python -m pytest tests/integration/source_collection/test_private_deletion.py tests/unit/source_collection/test_alembic_config.py -q

Expected: New persistence-focused tests PASS; the previously RED worker consumer scenarios remain RED until Task 3. The Alembic branch has only 0009_private_deletion_receipt as head.

- [ ] **Step 5: Commit**

    git add src/epick_engine/source_collection/persistence.py migrations/versions/0009_private_deletion_receipt.py tests/integration/source_collection/test_private_deletion.py tests/unit/source_collection/test_alembic_config.py
    git commit -m "feat(w2): private 삭제 receipt 저장"

### Task 3: Transactional consumer, private side-effect port, and race/replay protection

**Files:**
- Modify: src/epick_engine/source_collection/worker.py (PrivateDeletionSideEffects protocol and process_private_deletion)
- Modify: tests/integration/source_collection/test_private_deletion.py (existing RED scenarios and review-focus tests)

**Interfaces:**
- Produces: PrivateDeletionSideEffects with purge_private_references(*, owner_user_id: UUID, private_reference_keys: frozenset[str]) -> None and acknowledge(*, deletion_id: UUID, deletion_epoch: int) -> None.
- Produces: process_private_deletion(*, session_factory: sessionmaker[Session], command: PrivateDeletionCommand, side_effects: PrivateDeletionSideEffects) -> PrivateDeletionAcknowledgement.
- Consumes: Task 2 apply_private_deletion; no queue, AWS, W1 dispatcher, or public event dependency.

- [ ] **Step 1: Extend RED consumer tests**

    def test_stale_epoch_skips_purge_and_ack(session_factory) -> None:
        _process_private_deletion(session_factory=session_factory, owner_user_id=OWNER_A, deletion_id=FIRST_ID, deletion_epoch=7, attempt_ids=frozenset({ATTEMPT_A}), request_deduplication_ids=frozenset({DEDUP_A}), private_reference_keys=frozenset({"a-project-1"}), side_effects=effects)
        _process_private_deletion(session_factory=session_factory, owner_user_id=OWNER_A, deletion_id=LATE_ID, deletion_epoch=6, attempt_ids=frozenset({ATTEMPT_A2}), request_deduplication_ids=frozenset({DEDUP_A2}), private_reference_keys=frozenset({"a-project-2"}), side_effects=effects)
        assert effects.events == [("purge", (OWNER_A, frozenset({"a-project-1"}))), ("acknowledge", (ANY, 7))]

    def test_foreign_attempt_identifier_rolls_back_without_side_effects(session_factory) -> None:
        with pytest.raises(PersistenceConflict):
            _process_private_deletion(session_factory=session_factory, owner_user_id=OWNER_A, deletion_id=FOREIGN_ID, deletion_epoch=7, attempt_ids=frozenset({B1}), request_deduplication_ids=frozenset(), private_reference_keys=frozenset({"b-project-1"}), side_effects=effects)
        assert effects.events == []

- [ ] **Step 2: Run test to verify it fails**

Run: python -m pytest tests/integration/source_collection/test_private_deletion.py -q

Expected: FAIL until worker consumer and side-effect ordering are wired.

- [ ] **Step 3: Write minimal consumer implementation**

    def process_private_deletion(*, session_factory, command, side_effects):
        with session_factory() as session:
            with session.begin():
                outcome = apply_private_deletion(session, command)
        acknowledgement = PrivateDeletionAcknowledgement.from_command(command, outcome=outcome)
        if outcome == "STALE":
            return acknowledgement
        side_effects.purge_private_references(
            owner_user_id=command.owner_user_id,
            private_reference_keys=command.private_reference_keys,
        )
        if outcome in {"APPLIED", "DUPLICATE"}:
            side_effects.acknowledge(deletion_id=command.deletion_id, deletion_epoch=command.deletion_epoch)
        return acknowledgement

The owner scope lock is held through W2 deletion and receipt commit, not through an external W1 callback. A purge exception leaves the durable deletion and receipt intact but omits ACK. Same-command replay calls purge and ACK again from the durable DUPLICATE receipt. STALE or validation conflict invokes neither callback. Keep the old-epoch assert_current_attempt race from recreating deleted private state.

- [ ] **Step 4: Run test to verify it passes**

Run: python -m pytest tests/integration/source_collection/test_private_deletion.py -q

Expected: PASS for account scope, project scope, purge failure/no-ACK, replay, race fence, duplicate delivery, stale epoch, and foreign-owner rejection.

- [ ] **Step 5: Commit**

    git add src/epick_engine/source_collection/worker.py tests/integration/source_collection/test_private_deletion.py
    git commit -m "feat(w2): private 삭제 consumer 처리"

### Task 4: Promote migration head, pin CT15 preflight, and prepare W1 handoff

**Files:**
- Modify: src/epick_engine/source_collection/source_runtime_operator.py
- Modify: src/epick_engine/source_collection/commit_gate_operator.py
- Modify: tests/unit/source_collection/test_source_runtime_operator.py
- Modify: tests/unit/source_collection/test_commit_gate_operator.py
- Modify: tests/integration/source_collection/test_collection_runtime_storage.py
- Modify: tests/integration/source_collection/test_private_commit_gate.py
- Modify: contracts/w2-private/ct15-runtime.md

**Interfaces:**
- Produces: runtime/CT15 preflight acceptance only for 0009_private_deletion_receipt.
- Produces: W1 handoff naming schemas, consumer function, migration, outcomes, local commands, and excluded W1 responsibilities.

- [ ] **Step 1: Write failing head-pin and handoff assertions**

    def test_preflight_requires_private_deletion_receipt_head() -> None:
        with pytest.raises(SourceRuntimeConfigurationError, match="0009_private_deletion_receipt"):
            _symbol("preflight")(
                _engine(revisions=("0008_collection_runtime",)),
                _fake_sqs(),
                _settings(_config_payload()),
            )

    def test_ct15_contract_mentions_t067_schema_and_forward_head() -> None:
        document = CT15_RUNTIME.read_text(encoding="utf-8")
        assert "0009_private_deletion_receipt" in document
        assert "private-deletion-command.schema.json" in document
        assert "private-deletion-ack.schema.json" in document

- [ ] **Step 2: Run test to verify it fails**

Run: python -m pytest tests/unit/source_collection/test_source_runtime_operator.py tests/unit/source_collection/test_commit_gate_operator.py -q

Expected: FAIL because runtime and CT15 still pin 0008_collection_runtime.

- [ ] **Step 3: Update current-head references and handoff**

    _MIGRATION_HEAD = "0009_private_deletion_receipt"

Update each current-head fixture found by searching the literal 0008_collection_runtime, while retaining historical migrations that intentionally start at 0008. In ct15-runtime.md require migration to 0009 before CT15; W1 binds the W2 schemas inside its private outer envelope, dispatches authenticated commands to process_private_deletion, and retries transport/ACK failure with the same deletion_id. Explicitly exclude AWS, SQS, IAM, W1 dispatcher, and joint E2E from W2 completion claims.

- [ ] **Step 4: Run complete affected verification**

Run: python -m pytest tests/contract/source_collection/test_private_deletion_contracts.py tests/integration/source_collection/test_private_deletion.py tests/unit/source_collection/test_alembic_config.py tests/unit/source_collection/test_source_runtime_operator.py tests/unit/source_collection/test_commit_gate_operator.py tests/integration/source_collection/test_collection_runtime_storage.py tests/integration/source_collection/test_private_commit_gate.py -q

Expected: PASS; all current-head checks accept only 0009 and T067 behavior passes.

- [ ] **Step 5: Run quality checks and commit**

    ruff check src/epick_engine/source_collection tests/contract/source_collection/test_private_deletion_contracts.py tests/integration/source_collection/test_private_deletion.py
    ruff format --check src/epick_engine/source_collection tests/contract/source_collection/test_private_deletion_contracts.py tests/integration/source_collection/test_private_deletion.py
    git diff --check
    git add src/epick_engine/source_collection/source_runtime_operator.py src/epick_engine/source_collection/commit_gate_operator.py tests/unit/source_collection/test_source_runtime_operator.py tests/unit/source_collection/test_commit_gate_operator.py tests/integration/source_collection/test_collection_runtime_storage.py tests/integration/source_collection/test_private_commit_gate.py contracts/w2-private/ct15-runtime.md
    git commit -m "docs(w2): private 삭제 W1 인계 갱신"

## Self-Review

1. **Spec coverage:** Task 1 supplies versioned private-only command/ACK. Task 2 adds durable monotonic receipt and owner-scoped deletion. Task 3 covers ordering, failure/no-ACK, replay, race fence, and public-data preservation. Task 4 pins the new runtime head and W1 handoff. W1 outer-envelope/dispatcher/AWS work remains intentionally excluded.
2. **Placeholder scan:** Review every example against its named helper and existing fixture before dispatch; no deferred implementation marker remains.
3. **Type consistency:** Task 1 defines PrivateDeletionCommand/PrivateDeletionAcknowledgement; Task 2 consumes/produces them; Task 3 exports the same types; Task 4 publishes their schemas.
4. **Review Focus:** Each listed risk has a concrete test in Task 2, Task 3, or Task 4.
