# W2–W1 Private Authority Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect every W2 owner-private collection, gate, cleanup, and relay effect to the exact fresh W1 decision while preserving historical ACK replay across v2 deletion.

**Architecture:** A strict, one-shot W1 protected client validates five operation-specific response types; W2 then locks its owner state and rechecks durable bindings before mutation or SQS send. The existing collection attempt stores the first command–scope binding, while a forward migration lets deletion retain only the original ACK control graph without private result content.

**Tech Stack:** Python >=3.12,<3.13; Pydantic v2, SQLAlchemy 2/PostgreSQL, Alembic, stdlib HTTPS, pytest, Ruff, mypy. No new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-09-26-w2-w1-private-authority-runtime-design.md`

## Global Constraints

- Pin W1 implementation to full SHA `8d80a6f0edddd350a1e0308751fdb19bf7318d76`. The write/gate request and response models are the Pydantic classes in `backend/app/runtime/w2_private_write_authority.py` at that SHA; do not invent static schemas for them.
- Copy and SHA-256-check W1's six static current-write, gate-scope, and terminal-cleanup request/response schemas from `backend/contracts/w1/v1/` at the same SHA. Their ordered hashes are `6e408368995eba4d17144b963cf10c4ce11657e08ad8cacb93c566f1f4dd092f`, `7715bc88b2f293c571d95c60fead9d3bc9f5028e85e29e08003a1d089d693101`, `15ab35ae09dd449b4f0a7d0a0ba707508ef4110d0f898c17c84ca6e3185cf832`, `13615def394d4e0c48375a83fe1211574bc290bfbd6b4bbe8d8861ba13d2e3c0`, `e2d1127c07fb88df249b2bc1294cc930b1191560d04408499587fc54a361e913`, and `cfba5f5c3886291430ff096fb61e8f09640ddc02e83de4cab26bf87338bbba88`.
- The current-write scope lookup request contains only original owner, epoch, command, Job, and integer fence. Never infer ACCOUNT from nullable `project_ref`, URL, or payload; never probe candidate scopes. Its successful response is scope identity, not write authority.
- One W1 decision covers one logical W2 operation/transaction. Every later reservation, claim, heartbeat, replay, stage, release, gate application, relay claim/release, and actual send obtains its own decision. After the W1 call, lock the W2 owner row first and recheck the original binding and target row.
- `PREPARE`/`FINALIZE` require the current forward-write fence. W1-issued `ABORT`/`PURGE` and historical `ACK_RELAY` have distinct, narrower owner-lock policies. Terminal cleanup can release/tombstone existing rows only, never create a stage, apply a gate, or send.
- V2 deletion remains on its authenticated deletion-command/receipt path, not the general write-authority endpoint. Preserve original ACK message ID/body and minimal gate receipt/inbox/stage control identity without result payload until a separately approved bilateral count-only drain. No time-based automatic expiry.
- `401`/`403`/`422`, malformed 200, wrong echo, local mismatch, or unclassified scope fail closed. `503`/timeout may retry only the identical original binding and never mutate during the failed attempt.
- Use only an explicitly approved isolated PostgreSQL test database: `EPICK_TEST_DATABASE_URL` and `EPICK_TEST_DATABASE_APPROVED=1`. Never point tests at `EPICK_DATABASE_URL`; never persist bearer, DSN, live queue URL, or raw private payload in artifacts.
- Preserve the pre-existing uncommitted `docs/superpowers/plans/2026-09-23-w2-private-deletion-scope-v2.md`. Stage and commit only files owned by each task; do not push unless separately requested.

## Review Focus

1. A PROJECT dispatch with uppercase/noncanonical `project_ref` must fail instead of normalizing into W1's canonical UUID; Task 3 tests it.
2. A 200 scope response with a changed echo or unexpected `authority_ref` must not reserve; Tasks 1–3 test it.
3. A 503/timeout followed by cancellation must leave the original command unreserved and retry only its unchanged binding; Tasks 2–3 test it.
4. A STAGED relay claim racing v2 deletion must serialize on the owner row and never send after deletion commits; Task 8 tests it.
5. An ACK retry after deletion must use the original message ID/body; same ID with altered body is a conflict, not a fresh ACK; Tasks 6 and 8 test it.

## File and interface map

- `w1_private_authority_contracts.py` owns exact W1 request/response models, `W1PrivateBinding`, `W1GateBinding`, canonical scope parsing, echo checks, and fixed error mapping. It performs no I/O or database work.
- `w1_private_authority_client.py` owns one-shot HTTPS calls. It reuses the configured W1 lookup host, bearer, TLS and bounded transport conventions; no automatic retry, redirect, proxy discovery, or credential-bearing diagnostics.
- `private_scope.py` retains `PrivateWriteScope` for current writes and adds distinct gate/terminal decision values and owner-first lock policies. No persisted row or string `authority_ref` authenticates W1 by itself.
- `source_runtime_store.py` owns atomic initial attempt/scope storage and exact digest checks. `source_runtime.py` obtains a fresh W1 decision at each collection operation, including heartbeat thread and recovery.
- `commit_gate_store.py` and `source_runtime_gate.py` own exact gate APPLY; `commit_gate_runtime.py` owns STAGED/ACK relay claim, send, and release. `persistence.py` owns v2 deletion and the minimal ACK control graph.
- `source_runtime_operator.py` constructs and injects the production client, updates exact Alembic preflight, and keeps metadata-only preflight from granting runtime permission. CT15 and contract documentation receive the matching migration-head update.

---

### Task 1: Pin and decode W1's five private decision contracts

**Files:**
- Create: `src/epick_engine/source_collection/w1_private_authority_contracts.py`
- Create: `tests/contract/source_collection/test_w1_private_authority_contracts.py`
- Create: six `tests/fixtures/w1_private_contract/w2-{current-write-scope-lookup,gate-scope-lookup,terminal-cleanup-authority}.{request,response}.schema.json` files, copied byte-for-byte from the pinned W1 SHA

**Interfaces:**
- Produces: frozen `W1PrivateBinding(owner_user_id: UUID, owner_deletion_epoch: int, command_id: UUID, job_id: UUID, execution_fence: int)` with `from_collection(command: CollectionCommand)`, `from_gate(gate: CommitGateCommand)`, and `from_ack(ack: CommitGateAckProposal)`; and `W1GateBinding(private: W1PrivateBinding, operation_id: UUID, operation_revision: int, action: CommitGateAction, result_digest: str, purge_owner_deletion_epoch: int | None)` with `from_gate(gate)` and `from_ack(ack)`. Reject a noncanonical or out-of-signed-64-bit collection fence rather than coercing it.
- Produces: strict Pydantic pairs `CurrentWriteScopeLookupRequest/Response`, `PrivateWriteAuthorityRequest/Response`, `GateScopeLookupRequest/Response`, `GateAuthorityRequest/Response`, and `TerminalCleanupAuthorityRequest/Response` for their matching W1 schema versions. `validate_private_echo(request: BaseModel, response: BaseModel) -> None` rejects any changed request field while preserving the optional PURGE field's omitted-vs-present rule.

- [ ] **Step 1: Write failing contract tests.** `test_pinned_private_schema_hashes` checks the six SHA-256 values; `test_current_scope_cannot_carry_candidate_or_authority` rejects request `scope`/`project_ref` and response `authority_ref`; `test_private_response_rejects_wrong_echo_and_noncanonical_project` checks strict binding and UUID spelling. Assert W1 write/gate model field sets, non-PURGE omission and PURGE epoch rules from the pinned Pydantic source.
- [ ] **Step 2: Confirm red.** Run `.venv/Scripts/python.exe -m pytest tests/contract/source_collection/test_w1_private_authority_contracts.py -q`; expect missing module/fixtures, not an unrelated database skip.
- [ ] **Step 3: Add only the codecs and pinned snapshots.** Keep W1 error response codes fixed per route; use existing strict wire helpers where applicable and reject coercion of JSON bool/string to integer fence or epoch.
- [ ] **Step 4: Confirm green.** Run the same test command; expect all tests passed.
- [ ] **Step 5: Commit only this task's files.** Commit subject: `feat: W1 비공개 권한 계약과 해시 고정`.

### Task 2: Make one authenticated, bounded W1 authority call per request

**Files:**
- Create: `src/epick_engine/source_collection/w1_private_authority_client.py`
- Create: `tests/unit/source_collection/test_w1_private_authority_client.py`
- Modify only if needed for safe helper reuse: `src/epick_engine/source_collection/w1_lookup_client.py`, `tests/unit/source_collection/test_w1_lookup_client.py`

**Interfaces:**
- Consumes: Task 1 `W1PrivateBinding`, `W1GateBinding`, strict models and echo check.
- Produces: `W1PrivateAuthorityClient(endpoint: str, bearer: str, ssl_context: ssl.SSLContext, transport: LookupHTTPTransport | None = None)`; the `endpoint` is the already validated `W1_LOOKUP_ENDPOINT`, used only for its protected HTTPS origin. Client methods never accept arbitrary route strings.
- Produces: `W1PrivateAuthorityClient.lookup_current_scope(binding) -> CurrentWriteScopeLookupResponse`, `authorize_write(binding, scope: PrivateDeletionScope) -> PrivateWriteAuthorityResponse`, `lookup_gate_scope(gate, phase: Literal["APPLY","ACK_RELAY"]) -> GateScopeLookupResponse`, `authorize_gate(gate, phase, scope) -> GateAuthorityResponse`, and `authorize_terminal_cleanup(binding, scope, cleanup_kind) -> TerminalCleanupAuthorityResponse`.

- [ ] **Step 1: Write failing transport tests.** `test_private_client_posts_exact_protected_path_and_principal` checks the five paths and `X-EPICK-Service-Principal: w2`; `test_private_client_fail_closed_without_retry_or_secret_echo` covers 401/403/422, 503, timeout, malformed/oversized JSON, wrong content type, redirect, wrong echo, and bearer/endpoint redaction.
- [ ] **Step 2: Confirm red.** Run `.venv/Scripts/python.exe -m pytest tests/unit/source_collection/test_w1_private_authority_client.py -q`; expect absent client/methods.
- [ ] **Step 3: Implement the client.** Reuse W1 lookup's validated HTTPS origin, verified TLS context, injectable one-shot transport, bounded strict JSON decode, and fixed diagnostic conventions. Permit only the five literal protected targets; no live W1 call in unit tests.
- [ ] **Step 4: Confirm green.** Run the client tests plus `.venv/Scripts/python.exe -m pytest tests/unit/source_collection/test_w1_lookup_client.py -q`; expect passed.
- [ ] **Step 5: Commit only this task's files.** Commit subject: `feat: W1 비공개 권한 조회 클라이언트 연결`.

### Task 3: Bind first collection scope before reservation

**Files:**
- Modify: `src/epick_engine/source_collection/source_runtime.py:488-550`
- Modify: `src/epick_engine/source_collection/source_runtime_store.py:77-225`
- Test: `tests/unit/source_collection/test_source_runtime.py`
- Test: `tests/integration/source_collection/test_collection_runtime_storage.py`

**Interfaces:**
- Consumes: Tasks 1–2 current scope lookup and write-authority calls.
- Produces: `load_bound_collection_attempt(session, dispatch)` as the immutable replay source; `reserve_collection_attempt(..., private_scope: PrivateWriteScope)` still writes `private_scope_kind`, `project_id`, owner/Job, and `dispatch_digest` atomically in the existing attempt table. No first-binding migration.

- [ ] **Step 1: Write failing tests.** `test_first_reservation_requires_w1_scope_then_fresh_write_authority` parametrizes Core/direct × ACCOUNT/PROJECT and asserts lookup occurs before any DB mutation, exact null/UUID `project_ref` comparison, and one persisted attempt. `test_replayed_dispatch_cannot_change_original_scope_or_digest` rejects uppercase/noncanonical UUID, changed owner/Job/fence/epoch, missing ref, and changed scope without consuming observation order. Add a 200 wrong-echo and 503/timeout-then-cancel case with zero writes and no scope probing.
- [ ] **Step 2: Confirm red.** Run `.venv/Scripts/python.exe -m pytest tests/unit/source_collection/test_source_runtime.py tests/integration/source_collection/test_collection_runtime_storage.py -k "first_reservation_requires_w1_scope or replayed_dispatch_cannot_change_original_scope" -q`; expect failures, not skips for the PostgreSQL case.
- [ ] **Step 3: Resolve scope.** Initial dispatch: W1 command lookup, Task 2 current-scope lookup, strict response echo and received `project_ref` comparison, then a distinct fresh write-authority call. Existing attempt: reconstruct only its stored ACCOUNT/PROJECT scope after `dispatch_digest` comparison; never overwrite or reclassify `UNKNOWN`. Pass the new proof into the owner-locked reservation transaction.
- [ ] **Step 4: Confirm green.** Run the same focused command and existing reservation tests; expect passed.
- [ ] **Step 5: Commit only this task's files.** Commit subject: `feat: 최초 수집 scope와 명령 결속 영속화`.

### Task 4: Refresh authority at every collection transaction

**Files:**
- Modify: `src/epick_engine/source_collection/source_runtime.py:350-407,488-668,669-761`
- Modify: `src/epick_engine/source_collection/source_runtime_store.py:226-363`
- Modify: `src/epick_engine/source_collection/persistence.py:3960-4076,4077-4240`
- Test: `tests/unit/source_collection/test_source_runtime.py`
- Test: `tests/integration/source_collection/test_collection_runtime_storage.py`

**Interfaces:**
- Consumes: Task 3's immutable dispatch/scope binding and Task 2 `authorize_write`.
- Produces: collection handler receives an authority provider, not one reusable `PrivateWriteScope`. Store claim/renew/release receives an `expected_dispatch_digest: str` and verifies it under the owner-first lock; a proof still applies only to that store transaction.

- [ ] **Step 1: Write failing tests.** `test_each_collection_transaction_has_a_distinct_w1_decision` counts reservation, claim, heartbeat renewals, explicit renew, candidate commit, replay, and normal release. `test_revocation_between_claim_and_commit_prevents_public_and_private_writes` asserts no stage/pointer mutation, no reuse of an earlier `authority_ref`, and no stale-digest claim takeover.
- [ ] **Step 2: Confirm red.** Run `.venv/Scripts/python.exe -m pytest tests/unit/source_collection/test_source_runtime.py tests/integration/source_collection/test_collection_runtime_storage.py -k "distinct_w1_decision or revocation_between_claim" -q`; expect failures.
- [ ] **Step 3: Replace proof reuse.** Construct the existing `PrivateWriteScope(PrivateWriteAuthorityDecision(...))` only from a Task 2 validated write response. Fetch W1 outside each DB transaction and inside the heartbeat thread before its own renewal; then owner-lock and compare epoch, scope, digest, claim token and lease. Do not obtain one decision in `consume_source_runtime_once` and pass it through the entire handler. Keep failed/uncertain claims recoverable by DB-clock expiry.
- [ ] **Step 4: Confirm green.** Run focused and existing runtime storage tests; expect passed.
- [ ] **Step 5: Commit only this task's files.** Commit subject: `feat: 수집 단계마다 새 권한 결정 검증`.

### Task 5: Separate W1-issued gate APPLY from current-write proof

**Files:**
- Modify: `src/epick_engine/source_collection/private_scope.py`
- Modify: `src/epick_engine/source_collection/commit_gate_store.py:407-558`
- Modify: `src/epick_engine/source_collection/source_runtime_gate.py`
- Modify: `src/epick_engine/source_collection/commit_gate_runtime.py:219-276`
- Modify: `src/epick_engine/source_collection/source_runtime.py:669-761`
- Test: `tests/integration/source_collection/test_private_commit_gate.py`
- Test: `tests/unit/source_collection/test_commit_gate_runtime.py`

**Interfaces:**
- Consumes: Task 2 `lookup_gate_scope` and `authorize_gate(..., phase="APPLY", scope)`.
- Produces: immutable `PrivateGateAuthority.from_w1_response(response: GateAuthorityResponse)` carrying exact W1 response binding, action/phase/digest/scope; `lock_private_gate_scope(session: Session, decision: PrivateGateAuthority) -> None` locks owner first and applies current fence for PREPARE/FINALIZE, historical exact-binding policy for ABORT/PURGE. `apply_commit_gate` and `apply_collection_commit_gate` require this type, not `PrivateWriteScope`.

- [ ] **Step 1: Write failing tests.** `test_gate_apply_requires_independent_exact_authority` rejects a current-write proof, wrong operation/revision/action/digest/phase, unissued gate and wrong scope without ACK or public pointer change. `test_stage_less_abort_purge_resolves_scope_without_guessing` covers ACCOUNT/PROJECT, missing outbox, stale epoch, 403/503/timeout, and owner-lock race.
- [ ] **Step 2: Confirm red.** Run `.venv/Scripts/python.exe -m pytest tests/integration/source_collection/test_private_commit_gate.py tests/unit/source_collection/test_commit_gate_runtime.py -k "independent_exact_authority or resolves_scope_without_guessing" -q`; expect failures.
- [ ] **Step 3: Implement gate-only proof and lock policy.** Resolve scope from an exact persisted stage, otherwise W1 gate-scope lookup; compare echoed binding; obtain separate fresh APPLY authority before opening the owner-locked gate transaction. PURGE may not regress W2's deletion epoch or mint a new collection result; a missing stage may create only the existing ABORT/PURGE control shell.
- [ ] **Step 4: Confirm green.** Run focused and existing private-gate tests; expect passed.
- [ ] **Step 5: Commit only this task's files.** Commit subject: `feat: 발행된 commit gate 권한과 적용 경로 분리`.

### Task 6: Retain only the original ACK control graph across v2 deletion

**Files:**
- Create: `migrations/versions/0011_private_ack_control_retention.py`
- Modify: `src/epick_engine/source_collection/commit_gate_store.py:56-113`
- Modify: `src/epick_engine/source_collection/persistence.py:1358-1536`
- Test: `tests/integration/source_collection/test_private_deletion_scope_v2.py`
- Test: `tests/unit/source_collection/test_alembic_config.py`

**Interfaces:**
- Produces: `PrivateCommitStage.payload_purged: bool`, default false, with a forward-only check-constraint replacement: an active STAGED/PREPARED/FINALIZED row may have null `result_payload` only when marked purged; terminal ABORTED/PURGED rows still have null payload. The original ACK `message_id`, `payload`, receipt/inbox identity, and stage command/scope/digest survive deletion; STAGED outbox payload and all raw result content do not.

- [ ] **Step 1: Write failing migration/deletion tests.** `test_deletion_scrubs_payload_but_keeps_original_ack_control` covers account/project isolation, ACKs with either `delivered_at` value, same-ID/same-body replay, same-ID/different-body conflict, and no STAGED payload. `test_0011_forward_head_preserves_fk_and_check_constraints` upgrades 0010→0011 in an isolated schema and verifies metadata.
- [ ] **Step 2: Confirm red.** Run `.venv/Scripts/python.exe -m pytest tests/integration/source_collection/test_private_deletion_scope_v2.py tests/unit/source_collection/test_alembic_config.py -k "keeps_original_ack_control or 0011_forward_head" -q`; expect failures.
- [ ] **Step 3: Add the forward migration and scoped deletion.** Under the existing owner lock, keep only stages with original ACK control descendants, scrub their result/STAGED bodies, mark `payload_purged`, and preserve exact ACK/receipt/inbox links. Delete stages with no ACK and unrelated scoped private rows in the existing FK-safe order. Guard PREPARE/FINALIZE and staged replay against a purged payload. Do not infer W1 durable ACK consumption from SQS send or auto-expire controls.
- [ ] **Step 4: Confirm green.** Run focused and full v2 deletion tests; expect passed, including rollback/race checks.
- [ ] **Step 5: Commit only this task's files.** Commit subject: `feat: 삭제 후 원본 ACK 최소 제어 기록 보존`.

### Task 7: Restrict terminal cleanup to exact existing rows

**Files:**
- Modify: `src/epick_engine/source_collection/private_scope.py`
- Modify: `src/epick_engine/source_collection/source_runtime.py:468-485,639-666`
- Modify: `src/epick_engine/source_collection/source_runtime_store.py:340-363`
- Modify: `src/epick_engine/source_collection/commit_gate_store.py:199-225`
- Test: `tests/unit/source_collection/test_source_runtime.py`
- Test: `tests/integration/source_collection/test_collection_runtime_storage.py`
- Test: `tests/integration/source_collection/test_commit_gate_delivery.py`

**Interfaces:**
- Consumes: Task 2 `authorize_terminal_cleanup` and Task 6 purged-control marker.
- Produces: immutable `PrivateTerminalCleanupAuthority.from_w1_response(response: TerminalCleanupAuthorityResponse)` with exact W1 response `cleanup_kind` and `allowed_effect="OWNER_LOCKED_PRIVATE_CLEANUP_ONLY"`; `lock_private_terminal_cleanup_scope(session, decision) -> None` permits only a matching existing reservation, claim, or STAGED outbox release/tombstone under owner lock.

- [ ] **Step 1: Write failing tests.** `test_cancelled_claim_uses_cleanup_not_current_write` checks changed owner/Job/fence/epoch/scope and absent row denial. `test_terminal_staged_cleanup_never_sends_or_creates_gate` checks exact STAGED row, payload scrub, and no new ACK/result. A wrong `cleanup_kind` or allowed effect must fail.
- [ ] **Step 2: Confirm red.** Run the three listed test files with `-k "cancelled_claim_uses_cleanup or terminal_staged_cleanup" -q`; expect failures.
- [ ] **Step 3: Add the cleanup-only path.** Try fresh current authority only for an actually current release. Fall back to terminal cleanup only after an exact existing row is found and W1 semantically denies that current write; never fall back on 503, timeout, malformed response, or a local binding mismatch. Request the separate exact cleanup kind and recheck the stored original scope and target row. Leave uncertain cleanup for lease expiry/investigation; never use terminal authority for claim, stage, gate, or send.
- [ ] **Step 4: Confirm green.** Run focused and existing claim/terminal tests; expect passed.
- [ ] **Step 5: Commit only this task's files.** Commit subject: `feat: 종료된 비공개 행 정리 권한을 분리`.

### Task 8: Authorize STAGED and historical ACK relay at claim and send

**Files:**
- Modify: `src/epick_engine/source_collection/commit_gate_runtime.py:162-439`
- Modify: `src/epick_engine/source_collection/source_runtime.py:176-228`
- Test: `tests/integration/source_collection/test_commit_gate_delivery.py`
- Test: `tests/unit/source_collection/test_commit_gate_runtime.py`

**Interfaces:**
- Consumes: Task 5 `PrivateGateAuthority`, Task 7 terminal cleanup and Task 2 client. `relay_once(..., authority_client: W1PrivateAuthorityClient | None = None, before_send: BeforeSend | None = None)` fails closed without the client, uses current-write authority for STAGED and `phase="ACK_RELAY"` gate authority for ACK; an ACK with no exact local stage scope first uses W1 gate-scope lookup.
- Produces: one fresh decision for claim, another for release, and a separate fresh decision while the owner row remains locked through actual `queue.send` and completion-record attempt. Only exact persisted original message ID/body may be retried.

- [ ] **Step 1: Write failing tests.** `test_deleted_owner_ack_replays_original_wire` sends the retained ACK after deletion without using current-write lock. `test_stage_less_ack_scope_lookup_before_relay` checks ACCOUNT/PROJECT lookup, exact echo, missing historical outbox, 403/503/timeout, and no candidate probing. `test_staged_send_race_with_deletion_is_owner_serialized` blocks send after deletion wins. `test_send_commit_failure_retries_same_body_and_id` and `test_changed_ack_body_conflicts` cover uncertainty and tampering. Assert STAGED still also passes the existing W1 command lookup.
- [ ] **Step 2: Confirm red.** Run `.venv/Scripts/python.exe -m pytest tests/integration/source_collection/test_commit_gate_delivery.py tests/unit/source_collection/test_commit_gate_runtime.py -k "deleted_owner_ack_replays_original_wire or stage_less_ack_scope_lookup_before_relay or staged_send_race_with_deletion or send_commit_failure_retries_same_body_and_id or changed_ack_body_conflicts" -q`; expect failures.
- [ ] **Step 3: Split relay policies.** Do not reconstruct an authority from `PrivateCommitStage`; treat stage as scope/binding data only. Owner-lock and compare ACK action/revision/digest/outbox body before send, including a stage-less W1 lookup. On post-send DB failure, retain the same durable message; on denied STAGED, use only Task 7 terminal cleanup.
- [ ] **Step 4: Confirm green.** Run focused and full commit-gate delivery tests; expect passed.
- [ ] **Step 5: Commit only this task's files.** Commit subject: `feat: STAGED와 과거 ACK 전달 권한 분리`.

### Task 9: Wire the production operator and exact migration head

**Files:**
- Modify: `src/epick_engine/source_collection/source_runtime_operator.py:59,109-184,467-608,662-807`
- Modify: `src/epick_engine/source_collection/commit_gate_operator.py:64-115,203-233,319-430`
- Modify: `contracts/w2-private/ct15-runtime.md`
- Test: `tests/unit/source_collection/test_source_runtime_operator.py`
- Test: `tests/unit/source_collection/test_commit_gate_operator.py`
- Test: `tests/contract/source_collection/test_foundation_boundary.py`
- Test: migration-head assertions in `tests/integration/source_collection/test_collection_runtime_storage.py`, `tests/integration/source_collection/test_private_commit_gate.py`, and `tests/integration/source_collection/test_commit_gate_delivery.py`

**Interfaces:**
- Consumes: Tasks 2–8. `RuntimeDependencies` and `run_action` pass the same configured, one-shot client to collection, gate, and relay actions; individual calls remain fresh. Exact Alembic head becomes `0011_private_ack_control_retention`.

- [ ] **Step 1: Write failing operator tests.** `test_production_actions_inject_private_authority_client` checks consume-once, relay-once, and run; `test_missing_authority_dependency_fails_closed` checks no queue receipt deletion or send. `test_ct15_relay_requires_configured_w1_client` checks that its isolated consume/relay actions cannot bypass authority. Both preflights reject 0010 and accept only 0011 while remaining metadata-only.
- [ ] **Step 2: Confirm red.** Run `.venv/Scripts/python.exe -m pytest tests/unit/source_collection/test_source_runtime_operator.py tests/unit/source_collection/test_commit_gate_operator.py -k "inject_private_authority or missing_authority_dependency or preflight" -q`; expect failures.
- [ ] **Step 3: Connect production construction.** Use existing `W1_LOOKUP_ENDPOINT`, bearer and CA setting as the protected W1 origin; do not add a guessed service URL or secret. Pass the client through every general-runtime action. CT15 preflight/inspect remain metadata-only, but its consume/relay actions must receive the same explicit W1 configuration/client or fail closed. Update exact-head constants and affected contract/integration assertions, and document the new head/authority boundary without rewriting historical verification snapshots.
- [ ] **Step 4: Confirm green.** Run the operator and foundation contract tests; expect passed.
- [ ] **Step 5: Commit only this task's files.** Commit subject: `feat: 운영 runtime 권한 연결과 0011 사전 검사`.

### Task 10: Run full local verification and prepare a truthful W1 handoff

**Files:**
- Create: `tests/integration/source_collection/test_private_authority_runtime.py`
- Create after evidence exists: `docs/w2-w1-private-authority-runtime-handoff-2026-09-26.md`
- Modify only to fix demonstrated failures: files owned by earlier tasks

**Interfaces:** No new production interface. The handoff records exact W2 clean full SHA, W1 SHA/schema hashes, migration head, tested commands/counts, skips, runtime entrypoint/configuration *names*, count-only undelivered STAGED/ACK/cleanup state, and joint/AWS work still pending.

- [ ] **Step 1: Write the cross-seam regression test.** `test_core_direct_account_project_round_trip_with_revocation_and_restart` covers the four dispatch combinations, first reservation, fresh claim/heartbeat/stage, gate APPLY, deletion/terminal cleanup, and historical ACK relay using synthetic W1 responses and an approved isolated PostgreSQL schema. Include timeout before write and send-after-delete denial.
- [ ] **Step 2: Confirm red, then implement only missing direct consequences.** Run `.venv/Scripts/python.exe -m pytest tests/integration/source_collection/test_private_authority_runtime.py -q`; fail for a real seam gap, not for absent DB approval. Repair only that gap and rerun to pass.
- [ ] **Step 3: Run broad checks.** `.venv/Scripts/python.exe -m pytest tests/contract/source_collection tests/unit/source_collection tests/integration/source_collection -q`; `.venv/Scripts/ruff.exe check src tests migrations`; `.venv/Scripts/ruff.exe format --check src tests migrations`; `.venv/Scripts/mypy.exe src`. Record exact pass/fail/skip counts; if DB unavailable, label PostgreSQL checks unverified, not passed.
- [ ] **Step 4: Audit ripple and handoff.** Check every shared symbol/route/schema/head caller, `git diff --check`, current `git status`, no secrets/raw private content, unchanged user-owned dirty plan, and count-only replay state. W1/W2 joint round trip and AWS remain pending until independently executed.
- [ ] **Step 5: Commit verified test changes, then write and commit the handoff.** First commit subject: `test: W2 비공개 권한 런타임 통합 검증`; capture that clean code/test full SHA. The handoff names this preceding runtime SHA, then gets a separate `docs: W1 권한 연동 검증 결과 인계` commit; report both SHAs to W1 so the document never claims to contain its own SHA. Do not push or announce READY without separate authorization and evidence.
