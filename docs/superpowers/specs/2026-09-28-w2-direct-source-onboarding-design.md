# W1→W2 신규 공식 Source 자동 온보딩 설계

작성일: 2026-09-28
상태: W2 설계 검토안. W1 wire/API 수락 및 제품 구현 전이며 T050/T058 완료 증거가 아니다.
기준: EPick workspace의 `.agents/docs/W1_W2_Phase4_New_Source_Onboarding_Request_2026-09-28.md`(Engine 저장소 외부), W1 Service `d0ff44f8287305ed379ba6cfaa1fc403c0f875c2`, W2 Engine `536e31ccfb632c1285507eb7dbbfe0e7c8d3df81`.

## 목적과 제외 범위

사용자가 W1 공개 API에서 새 공식 정적 URL을 등록하면, W2가 사전에 승인한 **해당 기업·도메인·경로·자료 유형 규칙**에 정확히 부합하는 경우 W1과 같은 Company/Source ID로 등록하고, 사용자 건별 수동 SQL·설정 편집·worker 재시작 없이 수집을 시작한다. W1 FINALIZE 후 기존 W2 공용 outbox와 W3 경로를 통해 같은 Source ID가 READY에 도달해야 한다. 승인 규칙이 없거나 현재 권한·정책을 확인할 수 없으면 외부 요청 없이 보류한다.

이 범위는 정적 HTML 공식 Source 온보딩이다. RenderedCollector, 기존 private deletion·commit-gate 계약의 재설계, 모든 기업/URL 자동 허용, PDF와 접근 제한 우회는 포함하지 않는다. W1 요청서의 전체 T050/T058 및 실제 배포 검증을 이 문서만으로 완료 처리하지 않는다.

## 현재 상태 판정

`MISSING`. `source_runtime.py`는 `w1.private.w2.direct-source-registration.v1`을 수집 명령으로 라우팅하지만 등록정보 조회·W2 Company/Source 생성은 수행하지 않는다. `SqlAlchemyCollectionInputProvider.load`는 시작 시 고정된 `RuntimeSourceConfigFile.sources[source_id]`, W2 DB의 같은 Source/Company ID, 검증된 Company, 최신 `SourcePolicyDecision`을 요구한다. 기존 W2 공개 `POST /api/v1/companies/{company_id}/sources`는 W1이 발급한 Source ID를 받지 않는다. 따라서 현재 핀은 새 URL의 자동 등록·수집 경로가 아니다.

## 선택한 경계

기존 W1 direct-registration SQS 명령을 **등록 요청과 첫 수집을 묶은 단일 명령**으로 유지한다. URL·공식성·기업 근거는 SQS 본문에 추가하지 않는다. W2는 기존 W1 command lookup/currentness와 private-write authority를 통과한 뒤 신규 보호 등록정보 조회에서 해당 command에 결속된 metadata를 받는다. W1 `company_id`와 `source_id`를 W2의 PK로 그대로 사용하며, 별도 W2 UUID나 가변 ID 매핑을 만들지 않는다.

W2는 사전 승인 규칙, Source별 실행 설정, Source 정책과 등록 receipt를 자체 DB에 영속화한다. 정적 배포 파일은 claim lease와 전역 안전 상한·비밀값 없는 런타임 설정만 가진다. 현재 파일의 Source UUID별 immutable map은 동적 DB 조회로 대체한다. 새 규칙 자체의 승인·개정은 W2 운영자 전용 경계에서 감사 가능하게 수행한다. 사용자 URL 제출이 규칙을 만들거나 기존 규칙을 넓히지는 않는다.

## 제안 W1↔W2 wire 계약

W1이 이 계약을 수락하고 스키마를 고정하기 전에는 생산 wire로 사용하지 않는다. 아래 경로와 버전은 설계안의 정확한 제안 값이다.

| 경계 | 생산자 → 소비자 | 제안 계약 |
| --- | --- | --- |
| 기존 direct-registration dispatch | W1 worker → W2 collection command SQS | `w1.private.w2.direct-source-registration.v1` 유지. command/job/fence/owner epoch/Project/Company/Source/decision pin 결속을 변경하지 않는다. |
| 등록정보 보호 조회 | W2 → W1 `POST /internal/v1/w2-private/source-registration/lookup` | 요청 `command_id`, `execution_fence`, `owner_deletion_epoch`, `company_id`, `source_id`. 응답 `schema_version: w1.private.w2-source-registration-lookup.v1`, `status: AVAILABLE | UNAVAILABLE`; AVAILABLE에만 W1 canonical URL, W1 목적 유형, W1이 확인한 Company 공식 도메인·법인명·법인 식별정보·근거 참조, `registration_input_version`을 포함한다. W1은 현재 owner/Project/Job/command와 삭제 epoch를 검사하고 `canonical_url`에 schema와 별도 NORMATIVE semantic profile을 모두 적용한다. |
| 등록 상태 callback | W2 → W1 `POST /internal/v1/w2-private/source-registration/ack` | `schema_version: w2.private.source-registration-ack.v1`, `command_id`, `job_id`, `company_id`, `source_id`, owner/Project scope, fence, epoch, 등록정보 digest, 결과 `READY | HELD | REJECTED`, 고정 reason code. READY에만 양의 W2 정책 revision·승인 규칙 ID/revision을 포함한다. URL·원문·비밀값은 싣지 않는다. W1은 현재성 재검사 후 정확한 `200 {"status":"ACKNOWLEDGED"}`만 성공으로 반환하고 동일 ACK를 멱등 수락한다. |
| 수집 결과 | W2 → W1 기존 private staged-result/commit-gate | READY callback이 W2에서 확인 기록으로 영속화된 뒤에만 첫 fetch를 시작한다. 신규 등록 ACK가 FINALIZE를 대신하지 않는다. |

ACK reason code는 READY=`APPROVED`, HELD=`POLICY_RULE_MISSING | COMPANY_UNVERIFIED | URL_NORMALIZATION_MISMATCH | UNSUPPORTED_SOURCE_TYPE`, REJECTED=`SOURCE_ID_CONFLICT | CANONICAL_URL_CONFLICT | EXPLICIT_POLICY_DENIAL`로 제한한다. 조회 응답이 `UNAVAILABLE`이거나 W1 권한 응답이 403/409인 경우에는 등록 ACK를 임의 생성하지 않고 W1 currentness 실패로 처리한다. W1은 HELD/REJECTED를 Job의 수집 성공이나 READY로 해석하지 않는다. READY 후 실제 robots/redirect 검사 실패는 등록 ACK를 뒤집지 않고 기존 수집 실패 결과로 보고한다.

W2는 새 조회/ACK에도 기존 보호 HTTPS의 CA 검증, 고정 target, bearer, 응답 크기·시간 제한, redirect/proxy 금지 및 비밀값 없는 오류 규칙을 적용한다. W1의 기존 command lookup은 등록정보 조회나 W2 정책 승인으로 재해석하지 않는다. URL 원문은 보호 조회와 W2 비공개 저장소에만 존재하며 공용 증거·로그에 넣지 않는다.

W2 제안 lookup schema는 `contracts/w2-private/w1-source-registration-lookup.proposed.schema.json`이다. 파일명과 schema title/description대로 W1이 아직 수락하거나 pin하지 않은 **PROPOSED** 산출물이며 W1 정본이 아니다. 이 JSON Schema의 URL 검사는 구조 precheck일 뿐 DNS/IDNA, IP literal, port 범위를 완전하게 검증하지 않는다. Schema 단독 통과를 URL semantic 승인으로 해석해서는 안 된다.

`canonical_url`의 NORMATIVE 의미 검증 제안은 `contracts/w2-private/w1-source-registration-canonical-url.semantic-profile.proposed.md`이고 고정 합성 벡터는 `tests/fixtures/w2_source_onboarding/canonical-url-semantic-profile-vector.json`이다. W1은 schema와 이 profile을 함께 구현하고, 모든 accept vector의 reference output과 모든 reject vector의 실패를 교차 검증해 profile/vector SHA를 pin해야 한다. W1이 자기 저장소의 versioned schema·profile·fixture 경로와 SHA를 회신하기 전에는 runtime client를 활성화하지 않는다.

두 wire의 정수 lexical 규칙은 단일 NORMATIVE 제안 `contracts/w2-private/source-registration-json-integer-token.semantic-profile.proposed.md`와 `tests/fixtures/w2_source_onboarding/json-integer-token-semantic-profile-vector.json`에 고정한다. W1 lookup의 `execution_fence`·`owner_deletion_epoch`와 W2 ACK의 같은 두 필드 및 READY `policy_revision`·`approval_rule_revision`은 생산자가 부호·점·지수 없는 canonical unsigned decimal integer token으로 내보내야 한다. JSON Schema `integer`는 `1.0`·`1e0`을 수학적 정수로 수용할 수 있으므로 schema 단독으로 producer bytes를 인증할 수 없다. Strict consumer는 float가 되는 점·지수 표기를 거부하지만 `-0`은 decode 후 integer zero로 수락할 수 있으므로 universal lexical rejection을 주장하지 않는다. W1은 lookup producer vector와 canonical ACK compatibility를 교차 검증하고 profile/vector SHA 및 결과를 acceptance에 pin한다.

`registration_digest`는 AVAILABLE 응답에서 승인 판단에 사용하는 `company_id`, `source_id`, `canonical_url`, W1 목적 유형, `registration_input_version`, 기업 공식 도메인·W1 검증 법인명·법인 식별정보·근거 참조만의 SHA-256 소문자 hex다. 먼저 UUID를 소문자 정규형으로, 법인 식별정보·근거 참조 배열을 중복 없이 사전순으로 정규화한다. 그다음 모든 object key를 재귀적으로 정렬한 UTF-8 JSON(`ensure_ascii=false`, 공백 없는 `,`/`:` 구분자)을 해시한다. W1과 W2는 동일 벡터로 이를 검증하며, 조회 응답에 없는 임의 추가 필드는 digest나 승인 근거로 사용하지 않는다. W1 검증 법인명은 도메인이나 식별자에서 추론하지 않는다.

`company_legal_identifiers`는 W2 Company JSON의 `kind → value`를 손실 없이 전달하는 문자열 배열이며 각 항목은 정확한 `kind:value`다. 첫 `:`만 구분자로 사용하므로 value 내부 `:`는 허용한다. kind/value가 비거나 whitespace-only인 값과 양끝 whitespace가 있는 값은 거부하며 trim하거나 digest 입력을 재작성하지 않는다. `company_official_domain`, `company_legal_name`, `company_identity_evidence_refs`도 whitespace-only 또는 양끝 whitespace를 거부하고 원문을 자동 수정하지 않는다. 이 네 identity 입력은 AVAILABLE에만 완전하고 비어 있지 않게 존재해야 하며 UNAVAILABLE에는 필드가 `null`인 경우까지 금지한다.

W1 목적 유형은 `JOB_POSTING → job_posting`, `COMPANY_PROFILE → company_website`로만 매핑한다. 그 밖의 값, 또는 `COMPANY_PROFILE` 중 승인된 공식 기업 웹페이지 규칙에 맞지 않는 URL은 HELD다. W2는 semantic profile의 reference implementation인 `canonicalize_source_url`로 재정규화한 결과와 W1 canonical URL을 정확히 비교한다. 차이는 조용히 수정·합치지 않고 충돌로 보류하며, 양측 profile 버전·profile SHA·accept/reject vector SHA와 교차 결과를 계약 테스트에 고정한다.

## W2 승인 규칙과 데이터 원자성

W2 운영자가 승인하는 versioned 규칙은 기업의 공식 식별 근거, 정확한 HTTPS host, 경로 세그먼트 경계가 있는 허용 prefix 또는 정확한 경로, 허용 query 형태, W2 SourceType, 공식성·공개 접근·수집·발췌·본문 보존·재배포 판단과 근거, robots/redirect 적용 범위, 실행 limits, 활성 여부를 각각 가진다. host wildcard와 임의 정규식은 이 기능에 도입하지 않는다. query는 기본 거부하고 명시된 형태만 허용한다. 계열사 공유 host는 법인 식별 근거 및 경로까지 결속한다. 규칙 일치 자체가 현재 robots 허용을 대체하지 않으며 요청과 모든 redirect 목적지에서 기존 SSRF·robots·정책 검사를 다시 수행한다.

W2는 W2 owner 삭제 상태·Project tombstone row lock 및 W1 epoch를 검사한다. READY 분기에서는 하나의 짧은 DB transaction이 활성 승인 규칙 row lock, W1 Company ID에 대한 공식 식별 근거 일치/충돌 검사, W1 Source ID와 `(company_id, canonical_url)` 유일성 검사, Source 삽입 또는 정확한 replay 확인, 최신 `SourcePolicyDecision` 조회·필요한 경우에만 Source lock 아래 새 revision append, Source별 승인 실행 설정과 private 등록 receipt/ACK outbox 기록을 수행한다. 규칙 폐기·개정 writer도 같은 규칙 row lock을 사용한다. 다른 owner의 동일 승인 replay는 불필요한 정책 revision을 만들지 않는다. HELD/REJECTED 분기는 공용 Company/Source/Policy를 생성하거나 승인하지 않고 private receipt/ACK outbox와 고정 reason code만 기록한다. 등록 receipt는 command ID·W1 binding·metadata digest·결과에 결속되며 READY에만 정책/규칙 revision을 가진다. W2 Company가 없다면 W1의 확인 근거가 활성 W2 규칙의 법인 결속과 일치할 때에만 동일 UUID로 생성한다. 미확인 또는 동명 후보는 verified로 추정하지 않는다.

DB commit 후 W2가 READY callback을 보낸다. W1 수락 뒤 W2는 ACK 확인을 별도 transaction에 기록하고, 그 기록이 commit되어야 첫 fetch로 넘어갈 수 있다. READY인 SQS 메시지는 기존처럼 수집 결과가 영속 staged-result로 기록된 뒤에만 삭제한다. HELD/REJECTED 메시지는 W1이 해당 상태를 수락하고 W2 확인 기록이 commit된 뒤 fetch 없이 삭제한다. ACK 200 직후 W2 기록 실패/중단은 동일 digest callback의 멱등 재전달로 복구한다. W1 수락 후에도 W2는 fetch 직전 W1 권한·epoch와 W2 최신 정책/규칙/robots를 재확인한다. policy revision이 달라지면 기존 READY를 새 revision 승인으로 재해석하지 않고 수집 실패를 기존 정책 단계 결과로 W1에 전달하며 새 등록 판단을 요구한다. 이미 진행한 수집의 pointer 승격에는 기존 FINALIZE current-policy gate를 유지한다.

W1의 READY는 **등록 수락**이지 수집 또는 Job 완료가 아니다. W1은 기존 staged-result/commit-gate 결과로만 수집 완료를 판정한다. W2는 W1 callback 200 직후 owner가 삭제되거나 Project가 취소된 경우에도 fetch 전의 protected authority와 W2 tombstone 검사를 통과하지 못하면 수집하지 않는다.

## 실패·재시도·삭제

| 입력/사건 | W2 처리 및 W1에 보이는 결과 |
| --- | --- |
| 동일 command와 동일 metadata digest 재전달 | 동일 Source·receipt·ACK를 재사용한다. 완료된 수집은 기존 attempt replay를 따른다. |
| 동일 Source ID에 다른 URL/Company/유형, 동일 Company+URL에 다른 Source ID | 영구 충돌. 기존 Source를 덮어쓰거나 alias를 만들지 않고 REJECTED 및 고정 conflict code로 대조 요청한다. |
| 승인 규칙 없음, 기업 근거 미확인, W1/W2 URL 정규화 차이 | HELD. 외부 요청 없음. W1은 사용자에게 보류 상태와 정정/승인 후 재시도 행동을 표시한다. 새 판단에는 새 command/input version을 사용하되 같은 Source ID를 재사용한다. 동일 실패를 무한 자동 재전달하지 않는다. |
| 명시적 정책 거부, 현재 robots `Disallow`, 비허용 redirect | 명시적 정책 거부는 등록 REJECTED. READY 후 발견된 robots/redirect 거부는 기존 수집 단계 안전 실패로 보고한다. 접근 제한 우회·자동 재시도 없음. |
| 수집 단계 HTTP 429 | 기존 checkpoint와 사용자 요청 재시도 정책을 유지한다. READY가 자동 429 재시도 권한을 부여하지 않는다. |
| W1 조회/ACK 503·timeout | 동일 command/receipt로 제한적 재시도. 한도 초과는 DLQ·count-only 운영 점검 대상으로 남기며 성공으로 바꾸지 않는다. |
| W1 403·409, 삭제/취소 또는 fence/epoch 불일치 | 신규 수집 차단. W2 private receipt와 W1 상태를 대조해 terminal 또는 수동 조사 처리한다. |
| 등록/수집 도중 정책 revision 변경 | 새 revision을 무검증 적용하지 않는다. fetch 전 보류, 진행 중에는 기존 stage/currentness 및 FINALIZE gate를 적용한다. |

W2의 신규 owner/Project 결속 등록 receipt·ACK outbox는 v2 ACCOUNT/PROJECT 삭제 transaction의 분류·purge 대상이다. Project scope가 불분명하면 기존 방식대로 fail-close한다. W2는 삭제 tombstone과 W1 현재성을 등록 commit 전, callback에서, fetch 직전에 확인하고 늦은 replay가 개인 참조 또는 fetch를 복구하지 못하게 한다. 이미 적법하게 공유된 공용 Company/Source/SourceVersion은 다른 owner의 이용을 위해 보존하되 owner-private 상태와 로그는 삭제 범위를 따른다. 삭제·취소 후 신규 공개 Source의 W3 이벤트를 발행하지 않는다.

READY는 W3 입력이 아니다. 기존 W1 FINALIZE 이후의 W2 공용 outbox만 같은 Source ID의 버전/Evidence를 W3에 전달하며, W3 READY는 별도 실제 연동 검증으로 확인한다.

## 소유권과 변경 예상 위치

| 담당 | 구현 책임 |
| --- | --- |
| W1 | `backend/app/services/source_collections.py`/`backend/app/repo/source_collections.py`의 canonical URL semantic profile·Source/Company identity 결속과 검증 법인명 제공, `backend/app/runtime/workers.py`의 dispatch/currentness, `backend/app/runtime/lookup_adapter.py`와 보호 등록정보 조회, 등록 ACK 보호 route 및 owner/Project/epoch 검증, lookup/ACK JSON integer-token profile, versioned W1 schema/profile/fixture와 사용자 Job 상태. W1 DB를 W2가 직접 쓰지 않는다. |
| W2 | `source_runtime.py`/`source_runtime_operator.py`의 등록→ACK→수집 순서, `source_runtime_input.py`의 DB 기반 승인 설정, `w1_transport.py` 및 새 보호 조회/ACK client, `persistence.py`와 후속 migration의 규칙·per-Source 설정·private receipt/outbox, `private_deletion_v2.py` 연동, W2 schema/fixture/계약 테스트. W1 정책을 W2 승인 정책으로 추정하지 않는다. |
| W3 | 기존 W2 공용 outbox Source ID·revision 계약의 소비 검증. 등록 READY를 신규 분석 이벤트로 해석하지 않는다. |

신규 보호 route/schema/URL 및 JSON integer-token semantic profile은 W1의 수락과 각각의 pinned SHA가 필요하다. W2는 W1 합의 전 자체 테스트 seam과 명시적인 PROPOSED schema/profile/계약 초안까지만 검증할 수 있으며, 이 문서의 경로·필드를 이미 배포된 W1 계약이라고 주장하지 않는다.

배포 순서는 W1 보호 조회·ACK route와 계약 테스트를 먼저 배포하되 기존 W1 dispatch는 유지하고, W2의 새 DB migration과 새 runtime 이미지를 같은 head로 배포한 뒤 W1 신규 온보딩 경로를 활성화하는 것이다. 구 W2 runtime은 새 migration head에 호환된다고 간주하지 않는다. 이전 이미지로의 DB downgrade는 계획하지 않고, 오류 시 새 경로를 비활성화한 다음 forward corrective migration/이미지로 복구한다.

## 검증 및 릴리스 게이트

합성 fixture로 동일/충돌/정책 미확인·거부/robots·redirect/403·409·503·timeout/중복·역순·중단·재시작/정책 revision 변경/ACCOUNT·PROJECT 삭제/공유 Source를 검증한다. 격리 PostgreSQL과 실제 runtime 경계에서 사전 승인 규칙만 준비하고 **해당 Source ID·Source별 설정은 미리 주입하지 않은 채**, W1 공개 API 등록 → W2 READY ACK → 정적 수집 → staged-result → W1 FINALIZE → W2 outbox → W3 READY를 같은 핀으로 재현한다. URL·owner ID·본문·secret은 공유 증거에 남기지 않는다.

완료 보고에는 W1/W2/W3 full SHA, migration head, 확정된 schema/profile/vector 경로와 SHA256, URL 및 JSON integer-token profile 교차 결과, 테스트 명령·결과, 이미지 실행 시 immutable digest, count-only 상태를 포함한다. W1 보호 route·schema·semantic profile 수락, W2 구현, 실제 승인 Source와 robots 허용, 공동 실행 및 이미지 digest가 없으면 신규 온보딩은 `PENDING`이며 T050/T058 전체도 완료가 아니다.
