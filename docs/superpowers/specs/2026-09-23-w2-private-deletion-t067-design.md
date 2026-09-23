# W2 private deletion (T067) design

## Goal

Provide the W2-owned half of account- and project-scoped private deletion so
W1 can dispatch a fixed private command and receive an idempotent result.
Deletion removes only the named owner's W2-private collection state.  It never
deletes shared `Source`, `SourceVersion`, `Evidence`, retained public body, or
another owner's private state.

## Scope and ownership

W2 owns the payload schemas, consumer validation, transaction, persistent
currentness record, and regression evidence.  W1 owns the authenticated
deletion decision, private transport/dispatcher, retry scheduling, and the
outer W1 transport envelope.  This design deliberately does not reuse the
operation-local commit-gate `PURGE`: that action protects one staged result,
whereas T067 applies to a user or project deletion scope.

## W2 payload contract

`PrivateDeletionCommand` is a W2-owned, private-only payload with
`schema_version: "w2.private-deletion.v1"` and these fields:

| Field | Rule |
| --- | --- |
| `deletion_id` | UUID; stable across retries of one W1 deletion decision. |
| `owner_user_id` | UUID of the authenticated deletion owner. |
| `deletion_epoch` | Positive integer, strictly newer than the durable epoch recorded for that owner. |
| `attempt_ids` | Unique UUID collection-attempt identifiers in the W1-approved scope. |
| `request_deduplication_ids` | Unique UUID request-deduplication identifiers in the same scope. |
| `private_reference_keys` | Unique, non-empty private adapter reference keys to purge after database deletion. |

The command has no public Source, SourceVersion, Evidence, public event, or
public retained-body identifier.  The private channel and W1-authenticated
owner binding are required at the transport boundary; the W2 consumer also
checks that every affected database row belongs to `owner_user_id`.

`PrivateDeletionAck` is a W2-owned private payload with
`schema_version: "w2.private-deletion-ack.v1"`, `deletion_id`,
`owner_user_id`, `deletion_epoch`, and outcome `APPLIED`, `DUPLICATE`, or
`STALE`.  A retry of the same command returns its persisted ACK; a lower epoch
does not perform deletion or adapter purge.  An invalid command or a command
that conflicts with a persisted deletion id is rejected without ACK.

The precise W1 outer envelope/channel name is not part of this payload schema.
W1 must bind this versioned payload to its private, authenticated W1-to-W2
transport before dispatching it.

## Consumer transaction and recovery

The consumer will add a durable private-deletion receipt keyed by deletion id
and a per-owner monotonic deletion epoch.  In one W2 transaction it will:

1. validate the payload and lock the owner's current deletion epoch;
2. return the stored ACK for a byte-equivalent duplicate, reject a conflicting
   duplicate, and treat an older epoch as `STALE` without destructive work;
3. delete only owner-matching `CollectionAttempt` and
   `RequestDeduplication` rows named by the command, plus their W2-private
   payload/reference associations;
4. persist the new epoch and immutable ACK receipt; and
5. commit before invoking the W1-owned private-reference purge/ACK adapters.

If the private-reference purge fails, the consumer must not acknowledge the
transport message.  Retrying it must not recreate deleted W2-private data or
advance a lower epoch.  The adapter boundary is intentionally explicit so W1
can connect private checkpoint/cache cleanup and ACK publication without
placing those values in public events.

## Verification

The implementation must turn the existing T067 integration tests from expected
RED into passing coverage for account deletion, project deletion, owner
isolation, public-history preservation, purge failure/no ACK, worker-command
replay after deletion, concurrent late commit, duplicate delivery, and stale
epoch rejection.  Contract tests must validate valid, malformed, duplicate,
and stale command/ACK fixtures.  The W2 handoff to W1 must include the payload
schema paths, fixtures, tests, full commit SHA, and the exact limits above.

## Non-goals

- No W1 dispatcher, AWS queue, IAM, deployment, or teardown mutation.
- No public event emission and no disclosure of private command payloads.
- No claim that T067 end-to-end integration is complete until W1 binds the
  payload to its dispatcher and both sides run the dedicated deletion scenario.
