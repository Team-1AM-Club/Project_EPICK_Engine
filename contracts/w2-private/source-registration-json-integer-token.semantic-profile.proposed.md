# PROPOSED / UNPINNED NORMATIVE Source registration JSON integer-token profile

Profile ID: `w1-w2.private.source-registration-json-integer-token.semantic-profile.v1`

Status: **PROPOSED / UNPINNED**. W1 has not accepted or pinned this profile. It is not a deployed W1 contract.

## Normative scope

This single lexical profile applies to both directions of the proposed onboarding contract:

- W1 lookup response: `execution_fence`, `owner_deletion_epoch`
- W2 ACK request: `execution_fence`, `owner_deletion_epoch`, and READY-only non-null `policy_revision`, `approval_rule_revision`

For these non-negative fields, a canonical producer token is unsigned base-10 `0|[1-9][0-9]*`. A decimal point, exponent marker (`e` or `E`), sign, quoted number, boolean, or `null` is not a canonical producer token. Existing per-field value bounds still apply: `execution_fence`, `policy_revision`, and `approval_rule_revision` are at least `1`; `owner_deletion_epoch` is at least `0`.

JSON Schema `type: integer` validates mathematical value and may therefore accept decoded `1.0` or `1e0`. Schema validation alone is insufficient to certify producer bytes. The W1 lookup producer and W2 ACK producer MUST emit the canonical unsigned token form and MUST NOT emit a noncanonical spelling.

Consumers retain the existing semantic strict-integer validation. It rejects decimal-point and exponent spellings because JSON decoding produces a float, but it is not a universal raw-token validator: `-0` decodes to integer zero and may be accepted as zero. This profile does not claim otherwise and does not add a new raw parser. Interoperability depends on the two named producers emitting canonical bytes.

## Reference behavior and vectors

The W2 reference behavior is the existing strict `PositiveWireInt` / `NonNegativeWireInt` Pydantic validation used by `RegistrationMetadata` and `RegistrationAck`, together with W2's JSON serializer for outbound ACK bytes. This profile does not relax those types or claim that they preserve every raw lexical distinction.

The normative synthetic vectors are in `tests/fixtures/w2_source_onboarding/json-integer-token-semantic-profile-vector.json`. They cover every listed field with a canonical producer token and noncanonical decimal-point and exponent spellings, plus `-0` for the zero-valued epoch. Tests classify producer tokens independently, show that JSON Schema accepts the decoded mathematical value, verify the documented strict-consumer outcome, and require W2 ACK serialization to reproduce canonical bytes. The `-0` case explicitly records the consumer limitation instead of claiming rejection.

## Acceptance gate

W1 acceptance MUST pin its versioned lookup schema, this semantic profile, the vector file, and their SHA-256 values. W1 MUST demonstrate that its lookup producer emits the canonical token for every affected field and never emits a listed noncanonical producer token. W1 and W2 MUST also report compatibility with the canonical ACK vectors and the documented strict-consumer outcomes. Until that response changes acceptance from `PENDING` to `ACCEPTED`, this profile remains a W2 proposal and no live client/runtime path may rely on it.
