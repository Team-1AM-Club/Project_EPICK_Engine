# W2→W1 신규 Source 온보딩 계약 요청 (2026-09-28)

## 상태

- W1 acceptance: **PENDING**
- 이 문서는 W1의 구현·스키마 pin을 요청하는 제안이다. 현재 배포된 W1 계약이나 생산 route로 취급하지 않는다.
- W2가 직접 W1 DB를 쓰거나 이 문서를 독립적으로 W1에 발송하지 않는다.

## 제안 route와 wire

### 등록정보 보호 조회 — W1 소유 제안

- `POST /internal/v1/w2-private/source-registration/lookup`
- 요청: `command_id`, `execution_fence`, `owner_deletion_epoch`, `company_id`, `source_id`
- 응답 `schema_version`: `w1.private.w2-source-registration-lookup.v1`
- 공통 응답: `status`(`AVAILABLE | UNAVAILABLE`)와 요청의 다섯 binding field
- `AVAILABLE` 전용: `canonical_url`, `w1_source_type`, `registration_input_version`, `company_official_domain`, `company_legal_identifiers`, `company_identity_evidence_refs`
- `UNAVAILABLE` 전용: 비어 있지 않은 `reason_code`
- W1은 owner/Project/Job/command currentness와 삭제 epoch를 검사하고, W2는 응답을 기존 `w1.private.w2.direct-source-registration.v1` dispatch와 정확히 결속한다.

이 lookup schema는 W1이 자기 저장소의 versioned schema와 fixture를 게시하기 전까지 **PROPOSED / UNPINNED**다.

### 등록 상태 ACK — W2 소유

- `POST /internal/v1/w2-private/source-registration/ack`
- schema: `contracts/w2-private/source-registration-ack.schema.json`
- `schema_version`: `w2.private.source-registration-ack.v1`
- binding: `command_id`, `job_id`, `authenticated_owner_ref`, `project_ref`, `company_id`, `source_id`, `execution_fence`, `owner_deletion_epoch`, `registration_digest`
- 결과: `status`, `reason_code`, `policy_revision`, `approval_rule_id`, `approval_rule_revision`
- READY=`APPROVED`; HELD=`POLICY_RULE_MISSING | COMPANY_UNVERIFIED | URL_NORMALIZATION_MISMATCH | UNSUPPORTED_SOURCE_TYPE`; REJECTED=`SOURCE_ID_CONFLICT | CANONICAL_URL_CONFLICT | EXPLICIT_POLICY_DENIAL`
- READY에만 양의 policy/rule revision과 rule ID가 있고 HELD/REJECTED에는 세 필드가 모두 `null`이다.
- W1 성공 응답은 정확한 `200 {"status":"ACKNOWLEDGED"}`이며 동일 ACK를 멱등 수락해야 한다.

READY는 등록 수락일 뿐 수집 또는 Job 완료가 아니다. W2가 ACK 수락 확인을 영속화하기 전에는 첫 fetch를 시작하지 않으며, 기존 staged-result/commit-gate FINALIZE를 대체하지 않는다.

## digest profile과 합성 fixture

`registration_digest`는 AVAILABLE의 `company_id`, `source_id`, `canonical_url`, `w1_source_type`, `registration_input_version`, `company_official_domain`, `company_legal_identifiers`, `company_identity_evidence_refs`만 포함한다. UUID는 소문자 정규형, 두 배열은 중복 제거 후 사전순이며, object key를 재귀 정렬한 공백 없는 UTF-8 JSON(`ensure_ascii=false`)의 SHA-256 소문자 hex다.

- `tests/fixtures/w2_source_onboarding/registration-digest-vector.json`: `c6d22a87c3cb931953a0e38d9c7f270f63c876b6fb4054e6e48b48e8bc34477d`
- `tests/fixtures/w2_source_onboarding/registration-ack-ready.json`: `8eef215acf6d67cf794d41a53e760052210d901387f8452d01ef6bf1bd4cb2a4`
- fixture의 `.test` URL, UUID, 식별정보와 근거 참조는 모두 합성이며 실제 owner·기업·URL·비밀값이 아니다.

## W1 소유 변경 요청

W1은 아래 기존 정확한 파일 및 그 소유 경계에서 lookup/ACK currentness와 Source/Company 결속을 구현한다.

- `backend/app/services/source_collections.py`
- `backend/app/repo/source_collections.py`
- `backend/app/runtime/workers.py`
- `backend/app/runtime/lookup_adapter.py`

보호 route 파일, W1-owned lookup JSON Schema 및 동일 digest vector fixture의 최종 정확한 경로는 W1이 결정해 full SHA와 함께 회신해야 한다. W1은 canonical URL·Source/Company identity, owner/Project/Job/command, fence, deletion epoch를 재검사하고 HELD/REJECTED를 READY나 수집 성공으로 해석하지 않는다.

## W1 회신 게이트

다음 항목이 모두 제공되기 전 W2 runtime/client 연결과 신규 경로 활성화는 금지한다.

1. lookup/ACK route와 HTTP 동작의 수락 또는 수정안
2. W1-owned exact schema/fixture 파일 경로와 SHA-256
3. 동일 digest vector의 교차 검증 결과
4. owner/Project/currentness/deletion 검증과 동일 ACK 멱등성 테스트 결과
5. W1 acceptance 상태를 `ACCEPTED`로 바꾸는 명시적 회신
