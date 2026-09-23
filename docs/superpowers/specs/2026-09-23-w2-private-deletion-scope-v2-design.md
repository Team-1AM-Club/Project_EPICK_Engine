# W2-owned private deletion scope v2 design

## Purpose and decisions

The T067 v1 consumer at W2 `dbd698f801783ac6ad9d4840e49c841ec8f54c09`
deletes caller-named private row IDs. W1 cannot prove that its lists are
complete, especially for Project deletion: `request_deduplications` has no
Project attribution. An empty or incomplete list can therefore produce an
`APPLIED` acknowledgement while private data remains. W1 has correctly
disabled automatic dispatch of that contract.

This design makes W2 responsible for identifying and deleting its own complete
private scope. The user selected W2-owned enumeration, approved fail-closed
Project deletion when legacy row attribution is unprovable, and selected one
pending deletion epoch per owner until W1 purge and ACK complete. Success means
an authenticated account or Project deletion cannot leave W2-owned private
state in scope, recreate it through a late worker, delete another Project's
state, or remove shared public Source history.

The v1 design remains a record of the implemented baseline, not the production
scope contract. T050 operator wiring and T058 W1/W2/W3 end-to-end evidence are
separate tasks; this design establishes their deletion boundary only.

## Ownership and alternatives

W1 owns the authenticated deletion decision, owner/Project authorization,
stable deletion target and epoch, private transport envelope, dispatch and
retry, W1-owned reference purge, and final target ACK. W2 owns the versioned
payload and ACK schemas, its private-row inventory and Project attribution,
owner/project write fences, one-transaction deletion and durable receipt, and
its local regression evidence.

An authenticated W2 lookup followed by a W1 ID-list command was rejected
because a write can occur between lookup and deletion. Deleting every owner's
row for a Project request was rejected because it destroys other Projects'
state. W2 enumerates under a lock shared with every W2-private write instead.

## Private wire contract

The new private command has `schema_version: "w2.private-deletion.v2"`, a
canonical lowercase UUID `deletion_id`, canonical lowercase UUID
`owner_user_id`, a positive signed 64-bit `deletion_epoch` in
`1..9223372036854775807`, and exactly one scope:

| Scope | Payload | Meaning |
| --- | --- | --- |
| Account | `{"type":"ACCOUNT"}` | All user-private collection data of that owner; only minimal replay/tombstone control records remain subject to the privacy gate. |
| Project | `{"type":"PROJECT","project_id":"<canonical UUID>"}` | Only private state proven to belong to that owner and Project. |

The command contains no W2 row IDs, public Source IDs, or
`private_reference_keys`. Extra fields, malformed scope combinations, duplicate
or reused IDs with different content, noncanonical UUIDs, and out-of-range
epochs are rejected. W1's authenticated outer envelope must bind its owner,
deletion target, epoch, and scope to the inner payload; W2's production
consumer must reject v1 payloads rather than route them to the old list-based
deletion function. The W1 outer schema and message type are W1-owned but must
be pinned and cross-validated with W2 before dispatch.

The v2 private ACK echoes `deletion_id`, `owner_user_id`, `deletion_epoch`, and
scope, with outcome `APPLIED` or `DUPLICATE` for a completed W2 transaction.
`STALE` may be an internal result but never invokes W1 purge or publishes a
completion ACK. W1 accepts an ACK only for its still-current target and exact
owner, epoch, and scope. The v1 schema and fixture hashes remain immutable
historical artifacts; W1 must pin new v2 schema hashes and a new W2 full SHA.

## Complete W2-private inventory and attribution

The deletion inventory includes `collection_attempts`,
`request_deduplications`, `collection_runtime_attempts`, and
`private_commit_stages` with their private staged-outbox, ACK, receipt, and
inbox descendants. The implementation must audit any additional W2-private
table or payload introduced before activation. Public `Source`,
`SourceVersion`, `Evidence`, observations, public outbox, and permitted public
retained bodies are never deleted merely because a user or Project is deleted.

Every newly written private parent row carries an explicit, authenticated
scope classification: account-wide or a specific `(owner_user_id, project_id)`.
`collection_attempts.project_id` already exists but its null value alone is
not proof of account-wide scope. `request_deduplications`,
`collection_runtime_attempts`, and `private_commit_stages` need persisted
attribution; their descendants inherit the parent command's scope. A writer
must obtain this classification from the validated W1 command/authorization
context, never by guessing from `accepted_resource_ref`, source URL, job ID,
or JSON payload text. W1 must send a non-null, canonical Project identity for
Project-bound collection and retry writes. Account-wide writes must be
explicitly classified, not inferred from missing Project data.

For Project deletion, any private row of the owner whose Project relation
cannot be proven is a blocking `SCOPE_UNCLASSIFIED` condition. This includes
legacy null/unclassified rows in any inventoried private parent table. No
deletion, epoch advance, receipt, private purge, or completion ACK occurs.
Verified migration/backfill or operator remediation can establish the scope;
otherwise W1 keeps the target incomplete. Remediation may not relabel a row
from an untrusted resource string or erase another Project's data. Account
deletion needs no Project attribution and removes all of that owner's
inventoried private rows.

## Transaction, fences, and recovery

The W2 transaction obtains or locks the owner's deletion-state row first,
then any Project tombstone and affected private rows in a consistent order.
It verifies the immutable command digest and `(owner, epoch)` uniqueness.
For a new command it enumerates the complete applicable private scope under
that owner lock, checks attribution, deletes private descendants and parents,
records a durable account or Project tombstone plus the latest owner epoch,
and records a minimal immutable receipt before commit. Public history is
untouched. A conflict or `SCOPE_UNCLASSIFIED` rolls back every mutation.

Every W2-DB write path capable of inserting or reviving owner-private state,
including runtime reservation, staged-result/commit-gate storage,
request-deduplication, legacy collection commit, and replay, must acquire the
same owner lock before its other mutable locks. It rejects account-tombstoned
owners, writes to a tombstoned Project, and commands whose deletion epoch is
no longer current. If the writer commits first, deletion waits and sees its
row; if deletion commits first, the writer waits and then rejects. A worker
may still produce public, shareable Source data only when the normal
collection policy and its own authorization allow that independent write;
it must not re-create a deleted private result.

After the W2 transaction commits, W1 purges its own private references by
the authenticated account/Project scope, not by a W1-supplied list of W2 IDs.
Only successful purge permits W1 ACK application. A purge or ACK failure
leaves the W2 receipt intact and the W1 target pending. W1 retries the exact
same `deletion_id`, epoch, scope, and body. While that epoch is still latest,
W2 returns `DUPLICATE` and repeats the scope-based W1 purge and ACK steps
without repeating destructive DB work. A receipt below the latest owner
epoch is `STALE` even for the same deletion ID and never purges or ACKs.
W1 must not start another deletion epoch for the owner until the previous
purge and ACK have completed. This serialization is required; no implicit
carry-forward of an unfinished purge is assumed.

The receipt and tombstone contain only the identifiers, command digest,
scope, epoch, outcome, and timestamps needed for currentness/replay; never
the deleted payload, row lists, credentials, or raw personal content. Their
retention and backup-restoration treatment remain subject to the PRD G-04/G-07
privacy gate. Local contract success does not by itself authorize a production
claim of complete account deletion.

## Compatibility and rollout

W2 adds a migration after `0009_private_deletion_receipt` for scope
attribution and account/Project tombstones, then changes the exact DB-head
preflight to that new migration. Old v1 receipts remain distinguishable from
v2 receipts through a persisted contract-version column, backfilled as v1
for existing records. The migration also widens
`collection_attempts.owner_deletion_epoch` to signed 64-bit and validates
collection/runtime write epochs in `0..9223372036854775807`; zero is the
valid pre-deletion epoch, unlike the strictly positive deletion command. A v1
receipt must not be interpreted as proof that W2-owned
scope enumeration completed. New production dispatch remains disabled until
W1 pins the v2 schemas/manifest, adds its W2 deletion target and durable
dispatcher/ACK application, implements scope-based private-reference purge
and per-owner epoch serialization, and both sides agree on the outer
envelope. An isolated DB migration and immutable image pin precede joint
deletion tests; old `0008` CT15 and the `0009` local import check do not
establish v2 readiness.

## Verification and acceptance

Contract fixtures exercise canonical account/Project commands and ACKs,
schema/outer-scope mismatch, empty/extra fields, invalid UUIDs, signed-64-bit
boundaries, changed-body same-ID conflicts, and v1 production rejection.
Approved PostgreSQL integration tests cover account deletion of every
inventoried private table, Project-only deletion with another Project and
another owner preserved, unclassified legacy row rollback, public history
preservation, first-command concurrency, concurrent late reservations and
staged writes, same-body duplicate delivery, lower-epoch replay, purge/ACK
failure then same-command retry, and restart from a committed receipt.

W1/W2 joint evidence must show the exact v2 schema hashes, W1/W2 full SHAs,
DB head, immutable image digests, run ID, count-only before/after results,
and restart/replay observations. W1–W2 READY is not declared until a real
authenticated dispatcher and ACK path pass the account/Project scenarios.
T050 rendering/health/scheduler and T058 W3 READY/CT15 joint completion
remain separately gated.

## Non-goals

- No W1 Service code, AWS/SQS/IAM/deployment mutation, or teardown in this W2 design.
- No public deletion event or real personal payload in logs, public events,
  fixtures, or Git. Synthetic contract fixtures are permitted.
- No speculative legal retention period or assertion that the PRD G-04 gate has passed.
