# W2 → W1 비공개 권한 런타임 인계 (2026-09-26)

## 고정 기준과 현재 상태

- W2 Engine `feat/crawler` 코드·테스트 full SHA: `86a183fb9931973d898208b5db5f6e4beae6d8ff`.
- W1 비공개 권한 계약 pin full SHA: `8d80a6f0edddd350a1e0308751fdb19bf7318d76`.
- PostgreSQL migration head: `0011_private_ack_control_retention` (`down_revision=0010_private_deletion_scope_v2`).
- **W2 로컬 synthetic PostgreSQL 검증 결과이며 READY 판정이 아닙니다.** 실제 W1 응답·queue와 AWS workload-role 환경을 사용한 공동 검증은 아직 수행하지 않았습니다.

## W1 권한 계약 pin

아래 값은 `tests/fixtures/w1_private_contract/manifest.json`의 W2 권한 조회 6개 항목을 그대로 고정한 SHA-256입니다.

| Schema | SHA-256 |
| --- | --- |
| `w2-current-write-scope-lookup.request.schema.json` | `6e408368995eba4d17144b963cf10c4ce11657e08ad8cacb93c566f1f4dd092f` |
| `w2-current-write-scope-lookup.response.schema.json` | `7715bc88b2f293c571d95c60fead9d3bc9f5028e85e29e08003a1d089d693101` |
| `w2-gate-scope-lookup.request.schema.json` | `15ab35ae09dd449b4f0a7d0a0ba707508ef4110d0f898c17c84ca6e3185cf832` |
| `w2-gate-scope-lookup.response.schema.json` | `13615def394d4e0c48375a83fe1211574bc290bfbd6b4bbe8d8861ba13d2e3c0` |
| `w2-terminal-cleanup-authority.request.schema.json` | `e2d1127c07fb88df249b2bc1294cc930b1191560d04408499587fc54a361e913` |
| `w2-terminal-cleanup-authority.response.schema.json` | `cfba5f5c3886291430ff096fb61e8f09640ddc02e83de4cab26bf87338bbba88` |

W1은 공동 검증 전에 위 full SHA checkout과 여섯 schema hash의 일치를 독립적으로 확인해야 합니다.

## 검증한 runtime seam

`tests/integration/source_collection/test_private_authority_runtime.py::test_core_direct_account_project_round_trip_with_revocation_and_restart`는 격리된 PostgreSQL schema와 synthetic W1 응답만 사용해 다음 경계를 한 흐름으로 검증합니다.

1. Core/direct dispatch 각각의 `ACCOUNT`/`PROJECT` 조합 네 가지를 예약하고 claim한 뒤 heartbeat를 거쳐 `PERSISTED` stage로 전환합니다.
2. Core `PROJECT` proposal에 gate `APPLY`를 수행하고 권한 scope 결속을 확인합니다.
3. 현재 권한 조회 timeout이 DB write보다 먼저 실패하며, 삭제된 owner의 `STAGED` 결과는 외부 send 전에 거부되고 terminal cleanup으로 payload를 제거합니다.
4. `PROJECT` 삭제 후 ACK control row가 보존되는지 확인하고, 새 session factory로 재시작한 relay가 동일 ACK 식별자와 동일 wire body를 다시 전송하는지 확인합니다.

현재 HEAD에서 이 acceptance test는 첫 유효 실행부터 통과했습니다. setup identifier 오류와 test clock 누락으로 발생한 초기 test-harness 오류는 runtime RED로 간주하지 않았습니다. 따라서 이 Task에서 확인된 production seam gap이나 production 코드 변경은 없습니다.

## 검증 결과

- 집중 통합 테스트: `1 passed`.
- `tests/contract/source_collection`, `tests/unit/source_collection`, `tests/integration/source_collection` 전체: `2062 passed, 1 skipped, 8 failed, 4 warnings`.
- skip 1건: `test_real_browser_rendering_remains_explicitly_gated` — 승인된 Playwright package, browser executable, external-egress gate가 필요한 기존 명시적 gate.
- 실패 8건은 모두 기존 `RenderedCollector` 미구현 범주이며 이 Task에서 수정하지 않았습니다:
  - `test_rendering_requires_an_explicit_approved_js_decision_before_launch`
  - `test_approved_rendering_revalidates_redirect_dns_peer_and_every_subrequest`
  - `test_rendering_aborts_an_unsafe_subrequest_before_content_is_read`
  - `test_rendering_aborts_a_redirect_when_its_peer_differs_from_its_dns_result`
  - `test_rendering_aborts_a_redirect_that_reresolves_to_a_private_address`
  - `test_rendering_uses_a_fresh_nonpersistent_context_with_workers_and_downloads_disabled`
  - `test_rendered_429_is_one_browser_dispatch_without_a_candidate`
  - `test_rendering_cancellation_closes_resources_then_reaps_stubborn_child_before_reuse`
- Ruff 전체 check: 통과. Ruff 전체 format check: `155 files already formatted`.
- mypy `src`: `Success: no issues found in 36 source files`.
- `git diff --check`: 통과.

테스트 teardown 직전 synthetic schema의 count-only 상태는 다음과 같습니다. private body, token, endpoint 값은 기록하지 않습니다.

| 상태 | 미전달/정리 행 수 |
| --- | ---: |
| payload가 남은 undelivered `STAGED` | 2 |
| undelivered `ACK` | 0 |
| payload-purged cleanup/control stage | 2 |

## W1 배포 연결 정보

- runtime entrypoint: `epick-w2-source-runtime`
- required configuration names: `EPICK_DATABASE_URL`, `W2_SOURCE_RUNTIME_CONFIG_FILE`, `W1_LOOKUP_ENDPOINT`, `W1_LOOKUP_BEARER`, `W1_LOOKUP_CA_FILE`, `W1_COLLECTION_COMMAND_QUEUE_URL`, `W1_COMMIT_GATE_COMMAND_QUEUE_URL`, `W1_PRIVATE_INBOUND_QUEUE_URL`, `W1_EXPECTED_SYSTEM_SENDER_ID`
- 금지되는 static AWS configuration names: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_SECURITY_TOKEN`, `AWS_PROFILE`, `AWS_DEFAULT_PROFILE`, `AWS_SHARED_CREDENTIALS_FILE`, `AWS_CONFIG_FILE`, `AWS_CREDENTIAL_FILE`, `BOTO_CONFIG`

설정 값, DSN, token, queue URL, private payload는 이 문서에 포함하지 않았습니다. AWS 인증은 runtime이 허용하는 workload-role provider chain으로 공동 환경에서 확인해야 합니다.

## 남은 공동 Gate

- W1이 pinned full SHA와 여섯 schema hash를 독립 검증하고 synthetic가 아닌 실제 authority 응답을 제공해야 합니다.
- W1 command/private inbound queue와 W2 runtime 사이에서 네 dispatch 조합, timeout-before-write, send-after-delete denial, ACK restart relay를 공동 round trip으로 다시 확인해야 합니다.
- 실제 공동 환경에서 undelivered `STAGED`/`ACK` 및 cleanup row를 payload 없이 count-only로 확인하고 queue drain과 재전송 결과를 양측 SHA와 함께 남겨야 합니다.
- AWS workload-role, TLS/CA, network policy, queue permission, 배포·재시작 경로 검증이 남아 있습니다.
- 기존 `RenderedCollector` 8개 실패와 real-browser gate는 별도 소유 범위에서 해소해야 합니다.

위 공동 Gate가 모두 닫히기 전에는 W1/W2 private-authority runtime을 READY 또는 live 검증 완료로 선언하지 않습니다.
