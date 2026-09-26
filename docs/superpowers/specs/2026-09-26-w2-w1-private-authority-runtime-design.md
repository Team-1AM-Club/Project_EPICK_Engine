# W2–W1 private authority runtime design

> Draft for written-spec review. The user chose minimal ACK replay-control
> retention across v2 deletion. W1 has accepted that retention boundary and
> provided a protected canonical-scope lookup for gates without a local binding.
> These contracts are not yet implemented or jointly validated in W2.

## Purpose and boundary

W1 has implemented three authenticated private-authority decisions, but W2's
production source runtime does not yet use them at every owner-scoped operation.
W2 currently passes one private-write decision across several collection
transactions, and its relay reconstructs a `PrivateWriteScope` from a persisted
stage for both STAGED and historical ACK messages. The current-write fence then
rejects an ACK after owner deletion even when W1 authorizes that exact historical
ACK. The goal is to make fresh W1 decisions and W2's local locks agree at every
private mutation and send, without reopening new writes after cancellation or
deletion.

The user approved separate paths for current writes, W1-issued gate actions and
historical ACKs, and terminal cleanup. Success means no cached authority can
authorize a later transaction; terminal STAGED cannot be sent; a genuine
historical ACK remains retryable after deletion; and a terminal-cleanup decision
can only release or discard the exact existing row. W2 v2 deletion remains on
its authenticated deletion-command and receipt path, not these write-authority
endpoints.

W1's authoritative contract and implementation pin are in
[the 2026-09-26 W1 response](https://github.com/Team-1AM-Club/Project_EPICK_Service/blob/codex/008-phase4-us2/md/deploy/W1_W2_Phase4_T050_Authority_Clarification_Response_2026-09-26.md):
`14daafe22dbdfcb6aa7f3e78c6247fef1c2d2ea6`. This design concerns W2's
authority integration only. Rendered collection, scheduler, deletion consumer,
health endpoints, AWS deployment, and joint T050/T058 evidence remain separate
deliverables; authority integration does not mark them ready.

W1's [ACK-retention and gate-scope response](https://github.com/Team-1AM-Club/Project_EPICK_Service/blob/20a0c02ff09ebcb2dd45e814403325ee61a18aad/md/deploy/W1_W2_T050_ACK_Retention_And_Gate_Scope_Response_2026-09-26.md)
pins the scope-lookup implementation to
`a99de8d39a53444508c4ef2def427eb6ed3c1c91`. W1 reports focused
isolated-PostgreSQL verification (82 passed), not a W1/W2 round trip or
deployment.

The existing v2 deletion design's unconditional removal of ACK descendants is
superseded for an undelivered gate ACK. The user selected retention of only the
minimal replay-control records needed to finish that exact ACK, never the
original result payload. This is a narrow extension of the deletion boundary,
not permission for a post-deletion collection write.

## Selected approach

Use an authenticated W1 authority client with operation-specific decisions,
then apply a corresponding W2 local owner-lock policy. Do not extend the
existing `PrivateWriteScope` to mean historical ACK or terminal cleanup. A
persisted stage is a local binding record, never proof of W1 authorization.

Two narrower approaches are rejected: adding one HTTP check to the start of
`handle_collection_dispatch` would reuse a decision over reservation, claim,
renewal, stage, and relay transactions; adding a check only before `queue.send`
would leave relay claim/release and deleted-owner ACKs on the wrong lock path.
Neither meets W1's per-operation contract.

## W1 decision and W2 binding interfaces

The production adapter authenticates as the W2 service principal and invokes
the following protected W1 routes. It constructs a typed, operation-specific
decision only from a successful, validated response. Wire parsing or a local
`authority_ref` string never grants authority.

| W2 effect | W1 route and schema version | Required decision |
| --- | --- | --- |
| Current collection write, STAGED claim/send/retry | `POST /internal/v1/w2-private/authority`, `w1.private.w2-write-authority.v1` | Exact current owner, original epoch, command, Job, integer fence, and explicit ACCOUNT/PROJECT scope |
| PREPARE/FINALIZE/ABORT/PURGE apply | `POST /internal/v1/w2-private/gate-authority`, `w1.private.w2-gate-authority.v1`, `phase=APPLY` | Exact W1-issued operation ID, revision, action, result digest and original binding; PURGE also binds the new purge epoch |
| Gate ACK claim/send/retry | Same gate route, `phase=ACK_RELAY` | Exact ACK's issued operation/revision/action and original binding, supported by W1 historical outbox evidence |
| Existing terminal reservation, claim, or STAGED outbox cleanup | `POST /internal/v1/w2-private/terminal-cleanup-authority`, `w1.private.w2-terminal-cleanup.v1` | Exact binding and `cleanup_kind` of `RESERVATION_RELEASE`, `CLAIM_RELEASE`, or `STAGED_OUTBOX`; response effect must be `OWNER_LOCKED_PRIVATE_CLEANUP_ONLY` |

If a gate has no persisted W2 stage or other exact command-bound local scope,
W2 first invokes W1's protected
`POST /internal/v1/w2-private/gate-scope-lookup` with
`w1.private.w2-gate-scope-lookup.v1`. The request carries the original gate
owner, deletion epoch, command, Job, fence, operation, revision, action and
result digest; PURGE also carries its new deletion epoch. `phase=APPLY` is used
before applying a gate and `phase=ACK_RELAY` before sending its original ACK.
The request contains no proposed scope. W1 derives the canonical ACCOUNT or
PROJECT scope from the exact issued outbox, retained command/Job binding, and
owner/Project relation. W2 checks that every echoed binding field matches the
request exactly and uses the returned scope only for that same gate. The
lookup is **binding information, not authority**: a fresh gate-authority
decision is still required for each APPLY or ACK_RELAY operation. W2 never
probes guessed ACCOUNT/PROJECT candidates or derives scope from a null Project
reference, URL, or payload text.

The scope-lookup request and response schemas are pinned at W1 revision
`a99de8d39a53444508c4ef2def427eb6ed3c1c91` under
`backend/contracts/w1/v1/w2-gate-scope-lookup.{request,response}.schema.json`.
Their SHA-256 values are respectively
`15ab35ae09dd449b4f0a7d0a0ba707508ef4110d0f898c17c84ca6e3185cf832`
and `13615def394d4e0c48375a83fe1211574bc290bfbd6b4bbe8d8861ba13d2e3c0`.

The terminal-cleanup request and response are pinned to W1's
`backend/contracts/w1/v1/w2-terminal-cleanup-authority.{request,response}.schema.json`
with SHA256 respectively
`e2d1127c07fb88df249b2bc1294cc930b1191560d04408499587fc54a361e913`
and `cfba5f5c3886291430ff09640ddc02e83de4cab26bf87338bbba88`.
The implementation plan must pin and validate the write/gate request and
response schemas from that same W1 implementation revision before coding the
adapter. W2 must not synthesize scope from a null Project reference, URL, or
payload text: collection derives canonical binding from the validated W1
dispatch, and gate/relay derives it from the persisted W2 stage or another
exact command-bound local record and the gate or outbox record. An absent or
unclassified binding requires W1's canonical gate-scope lookup. A failed or
malformed lookup fails closed; its response cannot authorize a later gate.

## Operation order and local lock policies

One W1 decision covers one W2 owner-scoped logical operation/transaction with
one canonical binding. Multiple row mutations may share it only inside that
same transaction. Every subsequent transaction, lease heartbeat, release,
retry/restart, relay claim, relay release, and actual SQS send obtains another
decision. For ordinary DB operations the sequence is fresh W1 lookup, owner
state row lock first, local epoch/scope/binding and target-row recheck, then
commit. The W1 response is never cached for another operation.

- **Current write:** reservation, claim, each renew/heartbeat, normal release,
  replay, stage, and STAGED outbox transactions use the current-write decision
  and existing current-epoch/account/Project tombstone fence. A revoked or
  changed command, Job, fence, owner, epoch, or Project cannot create or send
  private state. A terminal normal release may instead request the precise
  terminal-cleanup decision for its already-existing row.
- **Gate apply:** each gate application transaction uses fresh `APPLY` authority
  and locks the owner before the command/stage rows. When local scope is absent,
  W2 resolves it through W1's gate-scope lookup before obtaining that separate
  authority decision. PREPARE and FINALIZE also
  require a current forward-write fence. W1-issued ABORT and PURGE may clean
  historical state after the original write becomes terminal, but only for
  their exact issued action and stage binding; PURGE also checks the new owner
  deletion epoch against W2's local fence. This permission cannot create a new
  collection stage or authorize arbitrary cleanup.
- **Historical ACK:** relay claim/release and send use `ACK_RELAY`, lock the
  owner row, and verify the persisted ACK, original stage binding, operation,
  revision, action, digest and unmodified outbox identity/content. This lock
  does not require the old epoch to remain current or the owner to be active;
  it cannot write a collection result. If the retained control record has no
  exact local scope, W2 resolves it through W1's `ACK_RELAY` scope lookup before
  seeking a separate fresh gate-authority decision. Missing owner/outbox or
  immutable gate identity, or missing W1 historical proof, denies relay.
- **Terminal cleanup:** the matching terminal-cleanup decision permits only
  owner-locked release/tombstone of the named existing reservation, claim, or
  STAGED outbox. The local check requires exact owner, original epoch, command,
  Job, fence, scope, row identity, and cleanup kind. It never stages, applies a
  gate action, or sends SQS. A denial leaves the row for lease expiry and
  investigation rather than converting cleanup into write authority.

For actual SQS send, relay holds the W2 owner lock through a **separate** fresh
W1 lookup, local outbox/binding recheck, send, and completion-record attempt.
Claim-time authority is insufficient. If SQS succeeds but the completion DB
commit fails, W2 retries the same persisted outbox ID and body; it does not
mint a new message or claim a successful local completion. Terminal STAGED
must be discarded through the cleanup path and is never sent using a past
claim or authority result.

## Deletion-time ACK survival

When an authenticated v2 deletion removes a private scope, it deletes raw
collection results and terminal STAGED payloads as before. Since W2 has no
exposed W1 durable ACK-application signal, the deletion transaction retains
the original ACK outbox message ID and body, immutable gate binding, and
minimal receipt/inbox replay-control identity for any ACK whose W1 durable
consumption has not been established by a separately approved bilateral
contract. A retained stage or equivalent control shell contains no result
payload and cannot be reopened for PREPARE/FINALIZE or STAGED send. This is not
permission to retain raw personal results indefinitely. The owner tombstone
and new epoch remain effective for current writes, while the historical-ACK
lock can match the original epoch and exact outbox.

A late, exact W1-issued ABORT/PURGE after deletion may create only the minimal
terminal gate/ACK control shell needed to acknowledge that issued action, after
fresh scope resolution (if needed), gate authority, and local owner/binding
checks. It cannot recreate a private result or STAGED payload.

W2 must not treat a successful SQS `send` or W1's SQS delivery deletion alone
as proof that W1 durably applied the ACK. The minimal control graph has no
time-based automatic expiry. Its removal requires separately approved
termination after bilateral count-only drain of outstanding STAGED/ACK/cleanup
rows, evaluation of W1 historical gate/outbox verification needs, and privacy
retention policy. W1 retains the original `JobCommand`/`Job` binding and
historical outbox/inbox evidence under its current policy; privileged removal
before the joint drain can make later lookups fail closed. Duplicate gate
delivery after v2 deletion reuses the same ACK message ID and identical body.
W1 then treats the same ID and digest as `DUPLICATE`; the same ID with a
different digest is `ID_CONFLICT`. Uncertain send or DB completion must not
mint a replacement ACK or private result.

## Runtime ownership and failure behavior

The adapter belongs at W2's production operator/dependency boundary. It must
be injected into the source runtime, gate consumer, and relay; test-only or
synthetic CT15 wiring is insufficient. The collection runtime must request a
decision at each transaction rather than accept one `PrivateWriteScope` for
the entire dispatch. Gate and relay consume distinct decision types and local
lock policies, while the existing W2 v2 deletion transaction remains separate.

W1 `401` (authentication), `403` (semantic denial), `422` (malformed request),
`503` (W1 DB failure), timeout, malformed success response, and W2 local
recheck failure all fail closed. None falls back to a wire field, cached
`authority_ref`, or generic current-write lock. Retryable failures leave
persisted leases/outboxes recoverable and require a new lookup; `403` does not
become permission for another effect. A separate exact terminal-cleanup query
may follow a denied current write only for an existing row and only where W1
permits that cleanup.

The scope lookup follows the same fail-closed rule: `403` is not a prompt to
try another scope, while `503` or timeout may retry with the unchanged original
gate binding and a new lookup. A scope-lookup success followed by gate-authority
`403` still forbids application or ACK send.

## Verification and handoff

Focused tests must show a new W1 call for every reservation, claim, heartbeat,
release, replay, stage, gate apply, relay claim/release, send, and retry;
accurate canonical request binding; owner-lock order; and no mutation/send on
denial, timeout, malformed reply, or local epoch/scope mismatch. PostgreSQL
tests must cover deleted-owner historical ACK replay, terminal STAGED discard,
W1-issued ABORT/PURGE after forward-write closure, ACK loss/restart, send
success followed by completion-commit failure, deletion with an undelivered
ACK, duplicate gate delivery after deletion, and writer/deletion ordering.
Stage-less ACCOUNT/PROJECT ABORT/PURGE must cover lookup then independent
authority, exact echoed binding, missing historical outbox, stale epoch,
different owner, `403`/`503`/timeout, and restart/replay. Tests must establish
that same-ID/same-body ACK replay is safe and same-ID/different-body is rejected.
Unit and contract tests pin W1 schema versions and both terminal-cleanup and
scope-lookup hashes. Joint W1/W2 verification must compare count-only drain
states without sharing raw private payloads.

The W2 handoff gives W1 a clean pushed full SHA, exact adapter and seam
inventory, W1 schema pins, Alembic head, focused/full test results and
remaining skips, runtime entrypoint and configuration *names*, and count-only
undelivered STAGED/ACK/cleanup evidence. It contains no credentials, raw
private payloads, DSNs, or live queue URLs. Joint AWS and T050/T058 readiness
remain pending until W1 independently validates that SHA and runs the shared
environment tests.
