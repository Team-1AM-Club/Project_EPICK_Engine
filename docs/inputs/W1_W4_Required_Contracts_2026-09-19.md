# W4가 W1에 반드시 제공해야 하는 계약·구현·검증 자료

작성일: 2026-09-18  
수신: W4 담당자  
요청: W1 담당자  
상태: **W1 검토 기준 제공 완료 / D01–D03 항목별 합의 대기 / W4 실제 producer 구현 대기**

## 0. W1 검토 기준 제공과 합의의 선행 순서

W4가 요청한 “W1 채택 schema 원본과 commit SHA”는 현재 제공할 수 있는 **채택 완료 산출물**이
아니다. 아직 D01 계약, D02 P1–P3 정책, D03 T1–T5 책임 경계가 합의되지 않았기 때문이다. W1은
아래 자료를 **채택 전 검토 기준**으로 제공한다. 이 표의 SHA-256은 파일 동일성 확인용이며,
후보 schema가 W1의 채택된 wire contract라는 뜻이 아니다.

| 구분 | 검토 기준 | 식별값 / W4 사용 규칙 |
| --- | --- | --- |
| W1 현재 기준 source | W1 현재 `develop` | full SHA `bb27a692cf002100a3f773df7e434e90fe03f83f`. 아래의 이미 채택된 W1 envelope/storage 계약을 재현할 기준이며, W4 question producer 채택 완료를 뜻하지 않는다. |
| W1 기존 envelope 경계 | `backend/contracts/w1/v1/private-message-envelope.schema.json` | tracked file SHA-256 `8119cb594782187669df608d6f1748c57c45130356998c7cd77867cdd9f80201`; W4의 private envelope, `producer=w4`, 전용 channel의 상위 경계 검토에 사용한다. |
| W1 기존 Core 저장 경계 | `backend/contracts/w1/v1/core-source-decision.schema.json` | tracked file SHA-256 `421cf7808c1e15758b9de1164b606f7007010636e3394befadb1f38ff5997b4e`; `QUESTION_MATCHING`과 `W4` owner 제약의 기존 저장 경계를 검토한다. |
| W1 기존 question fixture | `backend/contracts/fixtures/v1/w1/private-core-source-decision-question.json` | tracked file SHA-256 `805cdd8a88271ca5ea9f2712a5b6cec3c1bee2d8e72e361b08b892508d99ba7f`; producer 구현용 정본 fixture가 아니라 W1 existing consumer compatibility 검토용이다. |
| W1→W4 후보 wire schema | `specs/004-w1-w4-question-core/contracts/w4-question-core-decision.event.schema.json` | review SHA-256 `1eb0506d9b13e22198ea11fb5fccd628096de2903b0fe5b1da3d383928d8407a`; explicit `job_id`, null `company_id`, W4 owner, flat event를 제안한다. 아직 W1 tracked commit에 채택하지 않았다. |
| W1→W4 후보 채택 요청 | `specs/004-w1-w4-question-core/w4-adoption.md` | review SHA-256 `6b4bfe3b0796c376b9b5f2831e66aaf526c3f27f94e80f5112f2df0d559b537f`; D01–D03 합의 양식과 W1 제안 정책을 정의한다. |

W4는 위 후보 schema와 채택 요청 문서를 검토할 수 있으나, `bb27a69` 또는 review SHA만으로
“W1 채택 schema full SHA를 받았다”고 기록하면 안 된다. D01–D03 합의 후 W1은 합의된 schema,
정상·음성 fixture, consumer 검증을 tracked source에 반영하고 별도 full SHA를 제공한다.

### 0.1 지금 먼저 확정할 항목 (W1·W4·정책 승인자)

| 합의 항목 | 현재 W1 입장 | 최종 결정자 | 합의 전 안전 규칙 |
| --- | --- | --- | --- |
| D01 wire 계약 | `job_id` 필수, job 추정 금지, `message_id`/`decision_id` 분리, `QUESTION_MATCHING`, `decision_owner=W4`, `producer=w4`, `company_id=null`, owner/project/company hint 제외를 제안 | W1·W4 | 합의 전 W1은 후보 schema를 adopted로 표시하지 않고 W4 event를 실제 consumer에 연결하지 않는다. |
| D02 P1–P3 의미 정책 | 문서의 P1–P3을 제안하되, Core/Non-Core 의미와 reason code는 W1이 단독 확정하지 않는다 | 정책 승인자, W1·W4 | 승인 전 W4는 실제 사용자 자료에 자동 판단·발행하지 않는다. |
| D03 T1–T5 책임 경계 | 문서의 T1–T5 분리를 제안한다. 특히 W4 receipt는 W2 실행 재개가 아니며 explicit user retry만 새 fence/command를 만든다 | W1·W4 | W4는 W1 DB 쓰기, W1 queue receive/delete, purge 권한을 요구하지 않는다. |

### 0.2 합의 이후의 순서

1. W4가 §0 및 D01–D03에 대해 항목별 `채택 / 수정 / 보류`와 근거를 회신한다.
2. 정책 승인자가 P1–P3의 enablement 조건을 확정한다.
3. W1과 W4가 합의된 schema/fixture/codec을 각각 commit·push하고 접근 가능한 full SHA를 교환한다.
4. W4가 실제 producer·durable outbox·send-only relay를 제공한 뒤 W1이 실제 인증 lookup/consumer를 연결한다.
5. 고정된 양측 SHA와 실제 queue/principal로 공동 CT-12를 실행한다.

## 1. 목적

이 문서는 W4 Question Core Decision을 W1에 안전하게 연결하기 위해 W4가 W1에 반드시
제공해야 하는 항목과 수락 기준을 확정한다. 단순한 로컬 시연이나 설계 제안이 아니라, W1이
공유 계약을 채택하고 실제 consumer·PostgreSQL·SQS·W2 경계를 구현·검증할 수 있는 입력을
요청한다.

현재 W4 전달본은 스스로 다음 상태를 명시한다.

- `LOCAL_PARTIAL_INTEGRATION_PENDING_TEAM_ADOPTION`
- policy agreement `PENDING`
- W4 수신·영속 저장과 runtime row 저장은 모의 경계
- PostgreSQL, 실제 queue, 공동 CT-12 미실행
- 외부 발송·commit·push·배포 미수행

따라서 현재 전달본만으로 W1–W4 계약 채택이나 runtime 완료를 선언할 수 없다.

## 2. W4 필수 제공 항목

### D01. 후보 계약에 대한 항목별 채택 회신

W4는 다음 두 파일을 검토하고 각 항목을 `채택 / 수정 / 보류`로 회신해야 한다.

- `specs/004-w1-w4-question-core/w4-adoption.md`
- `specs/004-w1-w4-question-core/contracts/w4-question-core-decision.event.schema.json`

최소 회신 항목:

1. flat event 형식과 schema version
2. W1이 발급한 `job_id`를 trusted context로 받고 동일 값을 반환
3. `message_id`와 W4 `decision_id` 분리
4. `QUESTION_MATCHING`, `decision_owner=W4`, `producer=w4` 고정
5. question pin의 `company_id=null` 유지
6. owner/project/company hint를 W4 payload에서 제외
7. W4 전용 queue/principal 사용 및 W3 worker로 전송하지 않음
8. 동일 제출 재시도에서 ID·발생 시각·canonical body 불변 유지

수정 요청에는 정확한 필드, 형식, 의미, fixture와 호환성 영향을 함께 제공해야 한다. “전체
동의” 한 줄이나 구두 합의는 항목별 채택 근거를 대체하지 않는다.

**필수 이유**: W4 기존 payload에는 `job_id`가 없어 같은 question/source를 공유하는 여러 Job 중
어느 Job에 판단을 적용할지 안전하게 식별할 수 없다. W1은 question/source/owner 조합으로 Job을
추정하지 않으며 `job_id`가 없으면 fail-closed 처리한다.

**W1 수락 기준**: W4 회신이 `w4-adoption.md`의 A1 표 전체를 채우고, 이견이 있다면 합의된
schema revision에 반영되어 있어야 한다.

### D02. P1–P3 판단 정책의 소유자 결정

W4는 아래 의미 정책을 항목별로 채택하거나 수정안을 제시해야 한다.

| ID | 필요한 결정 |
| --- | --- |
| P1 | host가 승인한 문항/Source 근거만 판단하며 LLM `SUPPORTED`, 경험 우선순위, W3 C01 `USABLE`을 자동으로 Core로 변환하지 않음 |
| P2 | 평가 필수 자료는 `CORE_REQUIRED`, 맥락 보완 자료는 `NON_CORE_OPTIONAL`; 불명확하면 발행 보류 |
| P3 | Core reason 후보 `QUESTION_EVIDENCE_REQUIRED`, Non-Core 후보 `SUPPLEMENTARY_CONTEXT`; reason code에 원문·개인정보를 넣지 않음 |

W4 단독 결정이 아니라 product 승인이 필요하다면 승인 담당자, 현재 상태, 해제 조건과 목표
milestone을 기록해야 한다. 승인 전에는 실제 사용자 자료에 대한 자동 발행이 비활성 상태여야 한다.

**필수 이유**: 이 값들은 W4가 소유한 의미 판단이다. W1이 임의로 결정하면 미승인 product 정책을
공유 계약으로 고정하게 된다.

**W1 수락 기준**: P1–P3 각각에 채택/수정/보류와 담당자·근거·enablement 조건이 존재한다.

### D03. T1–T5 책임 경계의 항목별 합의

W4는 다음 책임 분리에 동의하거나 정확한 수정안을 제시해야 한다.

| ID | 책임 영역 |
| --- | --- |
| T1 W4 | 문항/Source 의미 판단, W1-issued `job_id` 보존, 불변 ID/body, durable outbox, 발행 직전 currentness 재검사, W4 main queue send-only relay |
| T2 W1 | transport 인증, Job/owner/project/question/Source/input/epoch/fence 검사, receipt·decision·binding 원자 저장, 사용자 retry와 W2 command/outbox·relay·lookup |
| T3 W2 | W1이 승인한 command와 protected lookup만 소비; W4 receipt를 수집 완료로 해석하지 않음 |
| T4 W3 | 분석 지식·사용 가능성 제공; W4 inbound나 W2 ACK를 W3 usability 계약으로 대체하지 않음 |
| T5 재실행 | W4 receipt만으로 실행을 재개하지 않으며 사용자의 명시적 retry가 새 fence와 W2 command를 생성 |

**필수 이유**: producer, consumer, W2 실행 책임을 섞으면 W4 판단 수신만으로 외부 수집이 자동
시작되거나 W1의 취소·삭제 fence가 우회될 수 있다.

**W1 수락 기준**: T1–T5 각각의 상태와 이견별 owner·해결 조건이 기록되어야 한다.

### D04. 채택된 schema와 정상·음성 fixture

W4는 채택된 계약과 정확히 일치하는 다음 산출물을 W4 저장소에 제공해야 한다.

- canonical JSON Schema
- valid `CORE_REQUIRED` fixture
- valid `NON_CORE_OPTIONAL` fixture
- missing/wrong `job_id`
- wrong producer/scope/owner
- non-null company, missing/wrong question
- wrong source/input
- zero/negative/stale/same revision
- decision-code/is-core mismatch
- unknown field, oversized body
- exact duplicate
- same message ID/different digest
- same W4 decision ID in another message
- W1과 W4가 동일 결과를 내는 canonical digest vector

모든 fixture는 합성 UUID와 비공개 내용이 없는 값만 사용해야 한다.

**필수 이유**: W2 R3-05는 W4→W1 schema, 정상/음성 fixture, input/owner/stale/dedup 규칙과
접근 가능한 pin을 요구한다. W1은 fixture 없이 W4 codec과 consumer가 같은 계약을 구현했는지
독립적으로 검증할 수 없다.

**W1 수락 기준**: W4 test suite와 W1 contract suite가 같은 fixture/digest를 통과하고, schema와
fixture의 SHA-256 provenance가 제공되어야 한다.

### D05. `job_id`가 결속된 실제 W4 producer codec

W4는 W1이 발급한 trusted decision context의 `job_id`를 사용해 채택된 flat event를 생성하는 실제
producer 코드를 제공해야 한다.

필수 동작:

- client/모델/자유 입력이 임의 `job_id`를 주입하지 못함
- owner/project/company를 W4가 추정해 payload에 싣지 않음
- current question, source, input, revision과 결속된 결정만 준비
- 철회·stale·인증 실패 시 event를 준비하거나 전송하지 않음
- body의 `producer=w4`를 transport 인증으로 오해하지 않음

**필수 이유**: W4의 현재 `core_decision.py`는
`W4_UNADOPTED_PROPOSAL_TRANSPORT_DISCONNECTED` 상태이며, 현재 전달본의 합성 생성기는 실제
producer가 아니다.

**W1 수락 기준**: 코드, 채택 schema, fixture, currentness 테스트가 동일한 접근 가능한 full SHA에
포함되어야 한다.

### D06. Durable producer outbox와 불변 재전송

W4는 실제 내구성 outbox를 구현해 다음을 증명해야 한다.

- decision과 outbound body를 DB의 한 확정 경계에서 `prepared` 상태로 보존
- stable `message_id`, `decision_id`, `occurred_at`, body, digest 보존
- attempt count, last error, prepared/sent 시각 등 안전한 retry metadata
- commit 뒤 process가 종료되어도 같은 body로 재전송
- SQS 응답 유실 또는 timeout 뒤에도 새 ID/body를 만들지 않음
- 성공적인 SQS acceptance 뒤에만 `sent` 상태로 전환
- private 원문·secret·token을 로그나 증거에 기록하지 않음

저장소 종류 자체를 W1이 지정하지는 않지만, process memory나 일회성 파일만으로 내구성을
주장할 수 없다.

**필수 이유**: DB 확정과 SQS 전송 사이에는 crash window가 있다. durable outbox가 없으면 판단이
유실되거나 재시도 때 다른 메시지로 변형될 수 있다.

**W1 수락 기준**: commit-before-send, send-response loss, process restart, duplicate retry에서
동일 ID/body/digest가 유지되는 자동화 테스트가 통과해야 한다.

### D07. 발행 직전 currentness 재검사와 send-only relay

W4 relay는 매 전송 직전에 다음을 다시 확인해야 한다.

- W1-issued Job context가 여전히 현재이고 철회되지 않음
- question/source/input/decision revision이 준비 시점과 일치
- W4가 필요한 처리 권한과 승인 상태를 유지
- stale/revoked 상태이면 SQS에 보내지 않음
- retry이면 기존 immutable body만 W4 전용 main queue로 전송

W4 실행 identity에는 W4 main queue의 `sqs:SendMessage`만 필요하다. W4 DLQ send, W1 queue
receive/delete, purge, W1 DB 쓰기 권한은 제공하지 않는다.

**필수 이유**: 준비 이후 전송 전까지 Job/질문/Source 관계가 바뀔 수 있다. 준비 시 한 번만 검사하면
stale 판단이 W1로 전달된다.

**W1 수락 기준**: stale input, revoked context, changed question/source와 restart retry 테스트가 있고,
send-only principal 및 대상 queue가 안전한 설정 이름으로 문서화되어야 한다.

### D08. 접근 가능한 commit full SHA와 재현 정보

W4는 D01–D07을 포함한 커밋을 push하고 다음을 제공해야 한다.

```text
W4 repository/access path:
W4 producer/outbox full SHA:
Schema path:
Valid fixture paths:
Negative fixture paths:
Producer codec path:
Outbox path:
Relay path:
Contract/currentness test command and exact result:
Outbox/restart test command and exact result:
Python/runtime version:
Safe environment variable names:
```

branch명, 로컬 미커밋 diff, ZIP 내부 branch label 또는 예정 SHA는 접근 가능한 full SHA를 대체하지
않는다.

**필수 이유**: W1과 W2가 동일 artifact를 독립 checkout하고 검증해야 하며, W2는 접근 가능한 수정
full SHA와 일치하는 runtime/schema/fixture를 요구한다.

**W1 수락 기준**: full SHA가 실제 접근 가능하고 그 revision에 보고된 파일과 테스트가 존재한다.

### D09. 공동 CT-12 참여 정보와 실제 실행 증거

W4는 실제 producer/outbox를 사용한 공동 CT-12에 참여해야 한다. W1 합성 sender만 실행한 결과나
W4 로컬 SQLite/모의 adapter 결과는 이를 대체하지 않는다.

필수 시나리오:

1. valid Core/Non-Core 생산과 전송
2. exact duplicate 10회 이상의 logical once
3. same ID/different body 및 same revision conflict
4. stale input/revision과 잘못된 principal 차단
5. W4 outbox commit 후 restart
6. W1 DB commit 후 queue delete 전 restart
7. 취소·owner 삭제를 W1 확정 전후에 주입
8. 명시적 user retry 전 W2 command가 0건임을 확인
9. user retry 뒤 W2 command/relay/protected lookup 확인
10. 관계 변경 뒤 relay/lookup 차단 및 다른 owner의 공유 Source 보존

W4는 실행 담당자, 가능한 milestone, 필요한 환경 변수명, 실제 producer image digest와 실행 로그의
안전한 요약을 제공해야 한다.

**필수 이유**: 로컬 mock은 actual producer, SQS acceptance, restart, PostgreSQL 원자성을 검증하지
못한다.

**W1 수락 기준**: 고정 W1/W4 full SHA와 immutable image digest, isolated DB/queue 식별자, 명령,
결과, row count 및 teardown 상태가 기록되고 모든 필수 시나리오가 통과한다.

### D10. 미완료 항목의 명시적 상태와 인계 조건

즉시 완료할 수 없는 항목도 누락하지 말고 다음 형식으로 제공해야 한다.

| 항목 | 현재 상태 | 담당자/책임 영역 | blocker | 준비 완료 기준 | 목표 milestone |
| --- | --- | --- | --- | --- | --- |
| 계약 채택 |  |  |  |  |  |
| P1–P3 승인 |  |  |  |  |  |
| producer codec |  |  |  |  |  |
| durable outbox |  |  |  |  |  |
| relay/IAM |  |  |  |  |  |
| joint CT-12 |  |  |  |  |  |

날짜를 확정할 수 없다면 임의 날짜를 만들지 말고 “어떤 조건이 충족되면 인계 가능한지”를 적는다.

**필수 이유**: W1과 W2가 준비된 계약과 기다려야 하는 runtime을 독립적으로 구분해야 한다.

## 3. W4가 제공할 필요가 없는 것

책임 범위를 넓혀 해석하지 않도록 다음은 W4 필수 제공 사항이 아니다.

- W1 PostgreSQL migration, RLS, inbox receipt 또는 binding 구현
- W1 consumer, DLQ 처리, Compose profile과 W1 receive/delete IAM
- W1의 Job/owner/company 관계 해석
- W1 user retry, W2 command/outbox, relay 또는 protected lookup 구현
- W2 commit-gate 내부 구현
- W3→W4 usability 계약 변경이나 Neo4j 연동
- 새 W1→W4 ACK API 또는 ACK queue
- 실제 secret, token, 운영 DB DSN 또는 사용자 원문

W4는 W1 내부 권한을 요구하는 대신 W4 전용 main queue의 send-only 권한만 사용한다.

## 4. 단계별 차단 기준

| Gate | W4가 제공해야 하는 것 | 미제공 시 결과 |
| --- | --- | --- |
| 계약 채택 | D01–D03 | W1은 후보 계약을 adopted로 표시하지 않으며 공유 schema 구현을 시작하지 않음 |
| W1 계약 구현 입력 | D04–D05와 접근 가능한 provenance | W1 contract/consumer가 W4 실제 codec과 일치한다고 주장할 수 없음 |
| W1–W4 runtime 준비 | D06–D08 | W1 isolated 구현과 별개로 W4 producer는 `PENDING` 유지 |
| 공동 검증 | D09 | `W1_W4_CT12_COMPLETE` 선언 금지 |
| W2 최종 인계 | D01–D10 및 teardown 증거 | `W2_HANDOFF_READY` 선언 금지 |

현재 task plan의 T004는 W4의 항목별 채택 회신과 접근 가능한 producer/outbox full SHA가 기록될
때까지 미완료다. 따라서 현 계획을 변경하지 않는 한 Phase 2 진입도 차단된다.

## 5. 근거

### W2 요청

- `md/orig2/W2_Implementation_Handoff_2026-09-18.md:55–59`: `QUESTION_MATCHING` null company와
  W2 UUID company 충돌, W1–W4 규칙 확인 및 runtime/schema/fixture가 일치하는 full SHA 요청
- 같은 문서 `:70–74`: R3-05의 W3/W4 inbound schema·fixture·pin·input/owner/stale/dedup 규칙,
  producer 준비 상태, CT-12 조건과 비밀값 금지

### W1 정본

- `specs/004-w1-w4-question-core/spec.md:119–139`: explicit Job binding, producer 검증,
  durable outbox, 운영 설정, 실제 transport CT-12와 full SHA 요구
- 같은 문서 `:168–177`: `job_id` 채택 가정, W3/W4 분리, durable producer 전 합성 경계,
  W4 담당자의 schema/fixture/outbox/full SHA/CT-12 책임
- `specs/004-w1-w4-question-core/plan.md:129–158`: no Job inference, 전용 인증 queue,
  producer-scoped identity, 원자 수신, 불변 재시도와 operational gate
- 같은 문서 `:223–237`: W1/W4 책임과 완료 상태
- `specs/004-w1-w4-question-core/tasks.md:181–187`: W4 소유 구현 T059–T063, full SHA 검증
  T064, 실제 producer 공동 CT-12 T065

### W4 자체 상태 선언

- `w4/EPICK_W1_W4_Question_Core_Local_2026-09-18/00-START-HERE.md:9`: W4 수신·영속화
  모의 경계, PostgreSQL·queue·팀 합의·공동 CT-12 미완료
- `w4/EPICK_W1_W4_Question_Core_Local_2026-09-18/SOURCE-STATE.json`: 상태
  `LOCAL_PARTIAL_INTEGRATION_PENDING_TEAM_ADOPTION`, policy `PENDING`, PostgreSQL/CT-12 `NOT_RUN`
- `w4/EPICK_W1_W4_Question_Core_Local_2026-09-18/Project_EPICK_Engine/docs/
  w4-question-core-integration-2026-09-18.md:46,63,78–81,93`: 실제 PostgreSQL·RLS·race,
  Job mapping, inbound persistence/outbox restart, 실제 queue와 공동 CT-12 미검증

## 6. W4 최종 회신 양식

W4는 아래 내용을 하나의 회신 문서로 제공하면 된다.

```text
1. D01 계약 항목별 채택/수정/보류:
2. D02 P1–P3 상태와 승인 owner:
3. D03 T1–T5 합의 상태:
4. D04 schema/fixture/digest 경로:
5. D05 producer codec 경로와 trusted job_id 주입 경계:
6. D06 durable outbox 경로와 restart 증거:
7. D07 currentness relay 경로와 send-only principal 설정명:
8. D08 repository와 accessible full SHA, 테스트 명령/결과:
9. D09 joint CT-12 담당자·가능 milestone·필요 조건:
10. D10 미완료 항목별 blocker와 준비 완료 기준:
```

이 회신에는 실제 secret, token, DB password/DSN 또는 사용자 원문을 포함하지 않는다.
