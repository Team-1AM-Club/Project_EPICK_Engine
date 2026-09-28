# PROPOSED W1 Source Registration Canonical URL NORMATIVE Semantic Profile

- Profile ID: `w1.private.w2-source-registration-canonical-url.semantic-profile.v1`
- Status: **PROPOSED / UNPINNED / W1 ACCEPTANCE PENDING**
- Scope: `AVAILABLE.canonical_url` in `w1.private.w2-source-registration-lookup.v1`
- W2 reference implementation: `epick_engine.source_collection.service.canonicalize_source_url`
- Fixed vectors: `tests/fixtures/w2_source_onboarding/canonical-url-semantic-profile-vector.json`

This profile is a W2 proposal for W1 review. It is not a deployed W1 contract. JSON Schema validation is only a structural precheck and is not sufficient to establish URL semantic validity.

## NORMATIVE acceptance and reference-output algorithm

An implementation MUST apply the following steps in order to the exact input string. A failure at any step rejects the URL. Implementations MUST NOT silently substitute a different input before validation.

1. Split the input as a URL and read its hostname and port. URL parsing failure or an invalid port representation/range rejects the input.
2. Compare the scheme case-insensitively with `https`. Any other or missing scheme rejects the input.
3. Require a hostname. Relative URLs and an empty authority/hostname are rejected.
4. Reject a username or password in the authority. Userinfo is never part of an accepted registration URL.
5. Normalize the hostname using this exact semantic profile:
   - Remove surrounding hostname whitespace and trailing dots.
   - If the result is an IPv4 or IPv6 literal accepted by standard IP address parsing, use its compressed lowercase representation.
   - Otherwise encode the hostname with IDNA, decode it as ASCII, and case-fold it.
   - Reject an empty result, a normalized hostname longer than 253 characters, or any empty label.
   - Reject a label longer than 63 characters, beginning or ending with `-`, containing characters other than ASCII letters, digits, or `-`, or containing non-ASCII after IDNA conversion.
6. Use port `443` when the input omits a port. An explicit port MUST be in the inclusive range `1..65535`.
7. Produce the reference canonical URL with scheme `https`, the normalized hostname, IPv6 brackets when required, and no explicit port when the effective port is `443`. Preserve the path (or use `/` when empty) and query exactly; remove the fragment.

The validation result and reference output MUST match every accepted and rejected fixed vector. An accepted input may differ byte-for-byte from the reference output, such as uppercase HTTPS/host, an IDN hostname, default port `443`, or a fragment. W2 validation does not rewrite the received lookup field: the exact W1-provided `canonical_url` remains the digest input and later W2 normalization-mismatch policy still applies.

## Combined contract rule

The lookup response is valid only when both conditions hold:

1. It passes `w1-source-registration-lookup.proposed.schema.json` structural validation.
2. Its `canonical_url` passes this semantic profile.

Schema-only acceptance MUST NOT be interpreted as semantic URL approval. In particular, DNS/IDNA label rules, IP literal parsing, and port range semantics are owned by this profile and its fixed vectors, not by a portable JSON Schema regular expression.

## W1 acceptance pin

Before W1 acceptance changes from `PENDING`, W1 MUST provide:

1. the W1-owned implementation and versioned contract path;
2. the accepted lookup schema SHA-256;
3. this semantic profile's accepted W1 path and SHA-256;
4. the fixed vector's accepted W1 path and SHA-256;
5. cross-implementation evidence that every accepted input yields the exact reference output and every rejected input fails;
6. confirmation that only URLs passing the combined schema and semantic profile are returned as `AVAILABLE.canonical_url`.

Until those pins exist, W2 client/runtime activation remains prohibited.
