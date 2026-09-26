# W2 → W1 비공개 권한 런타임 인계 (2026-09-26, 2026-09-27 갱신)

## 현재 정본 기준

- W2 Engine `feat/crawler` clean code/test full SHA: `3700b8dc324b4a365b19214550bd66b74171870b`.
- W1 비공개 권한 계약 pin full SHA: `8d80a6f0edddd350a1e0308751fdb19bf7318d76`.
- PostgreSQL migration head: `0012_private_ack_wire_digest` (`down_revision=0011_private_ack_control_retention`).
- 이 문서는 바로 앞 code/test SHA만 고정하며 문서 커밋 자신의 SHA를 주장하지 않습니다.
- **W2 로컬 synthetic PostgreSQL 검증 결과이며 READY 판정이 아닙니다.** 실제 W1 응답·queue와 AWS workload-role 환경을 사용한 공동 검증은 아직 수행하지 않았습니다.

## Superseded historical evidence

이 문서의 이전 revision이 고정했던 code/test SHA `86a183fb9931973d898208b5db5f6e4beae6d8ff`, handoff SHA `2648172133de635a7f670e445acf7fb7ba6dfe1b`, migration head `0011_private_ack_control_retention`은 0012 ACK wire digest와 CT15 authority-client 주입 이전의 역사적 증거입니다. 당시의 `1 passed` 집중 결과, `2062 passed, 1 skipped, 8 failed, 4 warnings` 전체 결과, Ruff format `155 files already formatted`도 그 revision에만 해당합니다. 이 값들을 현재 정본이나 현재 검증 결과로 사용하지 않습니다.

## W1 권한 계약 pin

`tests/fixtures/w1_private_contract/manifest.json`의 W2 권한 조회 6개 항목을 다시 읽고 실제 fixture 파일의 SHA-256까지 대조했습니다. 여섯 항목 모두 아래 manifest 값과 일치했습니다.

| Schema | SHA-256 |
| --- | --- |
| `w2-current-write-scope-lookup.request.schema.json` | `6e408368995eba4d17144b963cf10c4ce11657e08ad8cacb93c566f1f4dd092f` |
| `w2-current-write-scope-lookup.response.schema.json` | `7715bc88b2f293c571d95c60fead9d3bc9f5028e85e29e08003a1d089d693101` |
| `w2-gate-scope-lookup.request.schema.json` | `15ab35ae09dd449b4f0a7d0a0ba707508ef4110d0f898c17c84ca6e3185cf832` |
| `w2-gate-scope-lookup.response.schema.json` | `13615def394d4e0c48375a83fe1211574bc290bfbd6b4bbe8d8861ba13d2e3c0` |
| `w2-terminal-cleanup-authority.request.schema.json` | `e2d1127c07fb88df249b2bc1294cc930b1191560d04408499587fc54a361e913` |
| `w2-terminal-cleanup-authority.response.schema.json` | `cfba5f5c3886291430ff096fb61e8f09640ddc02e83de4cab26bf87338bbba88` |

W1은 공동 검증 전에 위 full SHA checkout과 여섯 schema hash를 독립적으로 확인해야 합니다.

## 0012 ACK canonical wire와 backfill 한계

- 신규 ACK는 JSON object를 key 정렬, 공백 없는 separator, 비 ASCII 문자 보존, NaN 거부 조건으로 canonical body로 만들고 `sha256:` 접두사와 소문자 SHA-256 hex로 `wire_digest`를 같은 transaction에 저장합니다.
- ACK load/replay는 저장 payload를 다시 canonicalize하고 `wire_digest`를 constant-time 비교한 뒤 ACK model 및 message/command 결속을 확인합니다. 저장 payload나 digest가 달라지면 외부 send 전에 fail closed 합니다.
- 0012 migration은 `private_commit_gate_acks.wire_digest`를 추가해 기존 JSON object ACK를 500개 batch로 backfill하고, 길이 71의 non-null column 및 digest-format check constraint로 고정합니다.
- **기존 ACK backfill 한계:** pre-0012 행은 migration 시점의 JSONB object에서 canonical wire를 재구성해 digest를 만듭니다. 따라서 JSONB가 잃은 과거의 원시 key order·whitespace나 이미 전송된 raw byte를 소급 증명하지 못하고, backfill 전에 발생했을 수 있는 변경 이력을 독립적으로 입증하지도 못합니다.
- legacy ACK payload가 JSON scalar 또는 array이면 canonical ACK object로 간주하지 않습니다. 0012 upgrade는 안전하게 중단·rollback되어 Alembic head가 0011에 남고 `wire_digest` column도 잔존하지 않습니다. destructive downgrade는 지원하지 않습니다.

## 검증한 runtime seam

`tests/integration/source_collection/test_private_authority_runtime.py::test_core_direct_account_project_round_trip_with_revocation_and_restart`는 격리된 PostgreSQL schema와 synthetic W1 응답만 사용해 다음 경계를 한 흐름으로 검증합니다.

1. Core/direct dispatch 각각의 `ACCOUNT`/`PROJECT` 조합 네 가지를 예약하고 claim한 뒤 heartbeat를 거쳐 `PERSISTED` stage로 전환합니다.
2. Core `PROJECT` proposal에 gate `APPLY`를 수행하고 권한 scope 결속을 확인합니다.
3. 현재 권한 조회 timeout이 DB write보다 먼저 실패하며, 삭제된 owner의 `STAGED` 결과는 외부 send 전에 거부되고 terminal cleanup으로 payload를 제거합니다.
4. `PROJECT` 삭제 후 ACK control row가 보존되는지 확인하고, 새 session factory로 재시작한 relay가 동일 ACK 식별자와 동일 wire body를 다시 전송하는지 확인합니다.

추가 focused 검증은 0012 정상 backfill/metadata, scalar·array legacy ACK의 safe-abort rollback, persisted ACK tamper rejection, ACK body conflict, unsupported downgrade, exact-head preflight, CT15 fault-control CLI authority-client 주입 및 누락 설정의 pre-transport failure를 포함했습니다.

## CT15 fault-control authority 결속

CT15 bounded fault-control CLI는 DB/queue preflight 뒤 동일한 configured W1 private-authority client를 한 번 생성합니다. retain 경로의 `consume_once`에는 `private_authority_client`로, ACK fault/relay 경로의 `relay_once`에는 `authority_client`로 주입합니다. W1 authority 설정이 누락되면 transport effect 전에 고정 실패로 종료합니다. 이 local fault control의 성공은 실제 W1/AWS 공동 성공을 뜻하지 않습니다.

## Fresh 검증 결과 — code/test SHA `3700b8dc324b4a365b19214550bd66b74171870b`

- cross-seam + 0012 migration/tamper/safe-abort + CT15 authority 주입 focused: `17 passed in 4.52s`.
- `tests/contract/source_collection`, `tests/unit/source_collection`, `tests/integration/source_collection` 전체: `2078 passed, 1 skipped, 8 failed, 4 warnings in 131.90s`.
- skip 1건: `test_real_browser_rendering_remains_explicitly_gated` — 승인된 Playwright package, browser executable, external-egress gate가 필요한 기존 명시적 gate.
- 실패 8건은 모두 기존 `RenderedCollector` 미구현 범주이며 이번 handoff에서 수정하거나 통과로 포장하지 않았습니다:
  - `test_rendering_requires_an_explicit_approved_js_decision_before_launch`
  - `test_approved_rendering_revalidates_redirect_dns_peer_and_every_subrequest`
  - `test_rendering_aborts_an_unsafe_subrequest_before_content_is_read`
  - `test_rendering_aborts_a_redirect_when_its_peer_differs_from_its_dns_result`
  - `test_rendering_aborts_a_redirect_that_reresolves_to_a_private_address`
  - `test_rendering_uses_a_fresh_nonpersistent_context_with_workers_and_downloads_disabled`
  - `test_rendered_429_is_one_browser_dispatch_without_a_candidate`
  - `test_rendering_cancellation_closes_resources_then_reaps_stubborn_child_before_reuse`
- Ruff 전체 check: `All checks passed!`. Ruff 전체 format check: `156 files already formatted`.
- bundled Python `-m mypy src`: `Success: no issues found in 36 source files`.
- `git diff --check`: 통과.

아래 수치는 현재 cross-seam test의 teardown 직전 assertion 증거일 뿐 live DB/queue snapshot이 아닙니다. private body, token, endpoint 값은 기록하지 않습니다.

| assertion 대상 | count |
| --- | ---: |
| payload가 남은 undelivered `STAGED` | 2 |
| undelivered `ACK` | 0 |
| payload-purged cleanup/control stage | 2 |

## Coordinated-stop 배포 순서

0011에서 0012로 올릴 때 mixed-version 또는 online write는 지원하지 않습니다.

1. 모든 W2 writer와 relay를 중지하고 in-flight 처리를 종료합니다.
2. 승인된 W2 DB에 0012 migration을 적용하고 exact head, 기존 ACK digest backfill, column/constraint를 검증합니다. preflight 자체는 migration을 수행하지 않습니다.
3. code/test SHA `3700b8dc324b4a365b19214550bd66b74171870b`의 새 binary를 배포하고 재시작합니다.
4. 새 binary의 exact-head 및 metadata preflight가 성공한 뒤에만 consumer와 relay 처리를 재개합니다.

backfill이 중단되거나 legacy ACK가 안전 중단 조건에 걸리면 runtime을 시작하지 말고 DB를 0011 상태로 유지한 채 원인과 행 범위를 private body 없이 별도 조정해야 합니다.

## Entrypoint와 configuration 이름

값은 이 문서에 기록하지 않습니다.

- entrypoint names: `epick-w2-source-runtime`, `epick-w2-ct15`, `epick_engine.source_collection.ct15_transport_controls`
- source-runtime required configuration names: `EPICK_DATABASE_URL`, `W2_SOURCE_RUNTIME_CONFIG_FILE`, `W1_LOOKUP_ENDPOINT`, `W1_LOOKUP_BEARER`, `W1_LOOKUP_CA_FILE`, `W1_COLLECTION_COMMAND_QUEUE_URL`, `W1_COMMIT_GATE_COMMAND_QUEUE_URL`, `W1_PRIVATE_INBOUND_QUEUE_URL`, `W1_EXPECTED_SYSTEM_SENDER_ID`
- CT15 required configuration names: `W2_CT15_ENABLED`, `W2_CT15_GATE_ONLY_QUEUE_APPROVED`, `W2_CT15_DATABASE_URL`, `W2_CT15_REGION`, `W2_CT15_COMMAND_QUEUE_URL`, `W2_CT15_INBOUND_QUEUE_URL`, `W2_CT15_EXPECTED_W1_SENDER_ID`, `W2_CT15_RUNTIME_LABEL`, `W1_LOOKUP_ENDPOINT`, `W1_LOOKUP_BEARER`, `W1_LOOKUP_CA_FILE`
- CT15 synthetic-control configuration names: `W2_CT15_SYNTHETIC_INPUTS`, `W2_CT15_TRANSPORT_CONTROLS`
- 금지되는 static AWS configuration names: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_SECURITY_TOKEN`, `AWS_PROFILE`, `AWS_DEFAULT_PROFILE`, `AWS_SHARED_CREDENTIALS_FILE`, `AWS_CONFIG_FILE`, `AWS_CREDENTIAL_FILE`, `BOTO_CONFIG`

DSN, token, queue URL, private payload 및 configuration 값은 포함하지 않았습니다. AWS 인증은 runtime이 허용하는 workload-role provider chain으로 공동 환경에서 확인해야 합니다.

## 남은 공동 Gate

- W1이 pinned full SHA와 여섯 schema hash를 독립 검증해야 합니다.
- W1 command/private inbound queue와 W2 runtime 사이에서 네 dispatch 조합, timeout-before-write, send-after-delete denial, canonical ACK restart relay 및 0012 digest 검증을 실제 authority 응답으로 공동 round trip 해야 합니다.
- coordinated-stop, 0012 backfill 결과, 새 binary exact-head preflight 및 rollback 중단 절차를 W1 운영 환경에서 검증해야 합니다.
- 실제 공동 환경의 undelivered `STAGED`/`ACK` 및 cleanup row는 payload 없이 count-only로 확인하고 queue drain과 재전송 결과를 양측 SHA와 함께 남겨야 합니다.
- AWS workload-role, TLS/CA, network policy, queue permission, 배포·재시작 경로 검증이 남아 있습니다.
- 기존 `RenderedCollector` 8개 실패와 real-browser gate는 별도 소유 범위에서 해소해야 합니다.

위 공동 Gate가 모두 닫히기 전에는 W1/W2 private-authority runtime을 READY 또는 live 검증 완료로 선언하지 않습니다.
