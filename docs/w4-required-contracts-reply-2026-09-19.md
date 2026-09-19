# W4 → W1 필수 계약 요청에 대한 항목별 회신 초안

> 이전 회신 기록이다. 추가 요청의 합의 선행 순서는 [r2 회신](w4-required-contracts-reply-2026-09-19-r2.md)에 반영했다.
> 후보 원문 검토·D01–D03 합의가 먼저이며 채택 완료 SHA는 합의 뒤 교환한다.

작성일: 2026-09-19. 대상: [W1 요청서 원본 사본](inputs/W1_W4_Required_Contracts_2026-09-18.md).
상태: **W4_REPLY_DRAFT / LOCAL_PRODUCER_VERIFIED / W1_ORIGINAL_SCHEMA_PENDING**.
외부 발송·공동 합의·commit/push·실제 queue 전송은 수행하지 않았다.

## 먼저 확인된 원본 범위

사용자가 제공한 Engine `16a7bd2653873a20a563e6d2f54c24c6dc18c373`은 **W2 인계 revision**이다.
해당 `contracts/w2-private/artifacts.sha256`의 81개 파일을 Git 원본 바이트로 재계산해 전부 일치함을 확인했다.
W2의 보고된 테스트 1006개를 재실행한 것은 아니다.

다음 두 W1 원본은 확인한 Service develop `9cbfa4284b5f74d2492618e71518ffe13d3b7a45`,
Service Core 작업 branch pin `5b056261591b91f8ed84ded50ee0f5885b92c58d`, 위 Engine W2 pin에 없다.
현재 작업 폴더에서도 찾지 못했다. 다른 revision에 없다고 단정하지 않는다.

- `specs/004-w1-w4-question-core/w4-adoption.md`
- `specs/004-w1-w4-question-core/contracts/w4-question-core-decision.event.schema.json`

[출처·체크섬 검증 기록](../samples/question-core-local/source-review.json).
따라서 아래는 **요청서에 명시된 항목에 대한 W4 입장**이며, 미열람 원본 A1 표 작성이나 W1 schema 채택 완료를 뜻하지 않는다.

## D01. 계약 항목별 회신

| 요청서 항목 | W4 회신 | 구현·해제 조건 |
| --- | --- | --- |
| 1. flat event와 schema version | **보류: flat 구조 수용, 정확한 버전 보류** | 원본 schema와 full SHA 수령 후 constants·필수 필드·길이·reason/digest 규칙을 대조해야 한다. 현재 TEST_ONLY 버전을 W1 정본으로 제출하지 않는다. |
| 2. W1-issued job_id 보존 | **채택** | host가 제공한 W1ContextPort에서만 받는다. public/client/model 입력으로 job_id를 전달하는 API를 만들지 않았다. 실제 인증된 context 획득 방식은 W1과 연결 필요. |
| 3. message_id와 decision_id 분리 | **채택** | 별도 UUID를 최초 준비 때 생성해 DB에 저장한다. 동일 제출 재시도에는 저장된 값을 재사용한다. |
| 4. scope/owner/producer 고정 | **채택** | QUESTION_MATCHING / W4 / w4 이외 schema는 거부한다. body의 producer 값을 인증으로 간주하지 않는다. |
| 5. company_id=null | **채택** | message에 null 유지. W1이 자신의 현재 관계로 수집 회사를 확인한다. |
| 6. owner/project/company hint 제외 | **채택** | wire에 싣지 않는다. context authorization_revision은 W1 host가 관계·권한·epoch/fence 변경을 반영해야 한다. |
| 7. 전용 queue/principal | **채택** | W4 main queue SendMessage만 사용한다. 실제 대상 ARN·role 및 W1 consumer의 인증 검증은 배포 전 확인 필요. W3 worker로 보내지 않는다. |
| 8. 동일 제출의 ID/시각/body 불변 | **채택** | SQLite 원자 저장, immutable trigger, stable submission key, 재시작·응답 유실 재전송 검사로 확인했다. |

schema 필드 수정안을 추정해 제시하지 않는다. 원본 수령 시 위 보류 항목과 최대 body 크기·canonicalization을 함께 확정한다.

## D02. P1–P3 정책

| ID | 상태 | 담당·근거 | enablement 조건 / milestone |
| --- | --- | --- | --- |
| P1 | **채택** | W4. host가 승인한 문항/Source만 사용하며 LLM SUPPORTED·경험 순위·C01 USABLE을 Core로 자동 변환하지 않는다. | 현재 코드도 명시적인 W4PolicyPort만 사용. 운영 정책 승인자는 팀에서 지정해야 한다. |
| P2 | **합성 검증에 채택 / 운영 보류** | W4 의미 정책, 제품 승인 담당자 미지정. 필수 CORE_REQUIRED, 보완 NON_CORE_OPTIONAL, 불명확하면 미발행. | 승인 담당자·판단 기준을 기록하고 검토 사례를 승인한 뒤 운영 활성화 검토. |
| P3 | **후보 수용 / 운영 보류** | W4. QUESTION_EVIDENCE_REQUIRED / SUPPLEMENTARY_CONTEXT만 합성 정책에서 사용하며 원문을 reason에 넣지 않는다. | W1 원본 schema와 제품 승인에서 reason enum·의미가 일치해야 한다. |

`PolicyDecision.approved`는 신뢰된 host policy adapter의 결과여야 한다. fixture의 true는 합성 검증 설정이다.
**REAL 자료 생성·발행은 계속 코드에서 차단**한다. 운영 승인이 나도 별도 검토 없이 이 제한이 자동 해제되지 않는다.

## D03. T1–T5 책임 회신

| ID | W4 입장 | 담당 / 미해결 조건 |
| --- | --- | --- |
| T1 | **채택** | W4가 의미 판단, trusted job_id 보존, stable ID/body, durable producer outbox, currentness recheck와 send-only relay를 맡는다. 로컬 구현 완료 범위와 실제 context 연결 대기를 아래에 구분한다. |
| T2 | **채택** | W1 transport 인증, 현재 관계·입력·epoch/fence 검사, receipt/decision/binding 원자 저장, retry/W2 실행 경계는 W1 담당. W4가 W1 DB에 쓰지 않는다. |
| T3 | **채택** | W2는 W1 command와 protected lookup만 소비. W4 전송 성공을 수집 완료로 해석하지 않는다. W2 최종 확인은 W1 취합 필요. |
| T4 | **채택** | W3 지식/usability와 W4 Core inbound는 별도 경계. W3 담당자의 계약 변경을 대행하지 않는다. |
| T5 | **채택** | W4 수신이나 SQS acceptance가 W2 실행을 재개하지 않는다. 새 fence·W2 command는 W1의 명시적 user retry 경계가 소유한다. |

위 표는 W4의 수용 입장이다. W1/W2/W3의 실제 합의를 대신 기록하지 않는다.

## D04. schema·fixture·digest

**W1 canonical schema: 미확보. W1 contract suite 동시 통과: 미실행.**

- [TEST_ONLY schema](../samples/question-core-local/test-only.schema.json): 로컬 독립 구현 검사용. W1 schema version을 추정하지 않고 별도 test-only 값을 사용했다. 실제 SQS adapter는 이 규격을 거부한다.
- [Core](../samples/question-core-local/core-required.json) / [Non-Core](../samples/question-core-local/non-core-optional.json): 합성 UUID, 비공개 원문 없음.
- [음성 fixture 22개](../samples/question-core-local/negative-events.json): schema 거부 18개와 context 결속 거부 4개.
- [digest vector 3개](../samples/question-core-local/digest-vectors.json) / [파일 SHA-256](../samples/question-core-local/manifest.json).
- stale/same revision, exact retry 10회, 같은 message ID/다른 body, 같은 W4 decision ID/다른 message의 상태를 [자동화 테스트](../tests/test_question_core_producer.py)에서 생성·검증한다.

3개 digest는 확인한 Service `9cbfa428…`의 기존 `core_decision_payload_digest` 함수와 일치한다.
이 함수는 기존 공통 계산 함수이며 **004 W4 consumer가 같은 fixture를 통과했다는 뜻이 아니다**.
원본 수령 후 canonical schema와 fixture를 확정해 양측 suite에서 같은 결과를 확인해야 한다.

## D05. job_id 결속 producer

[question_core_contract.py](../epick_w4/question_core_contract.py),
[question_core_producer.py](../epick_w4/question_core_producer.py).

`prepare(submission_key=..., context_key=...)`가 trusted host의 W1 context와 W4 policy를 조회한다.
client/LLM이 job_id·source·question·입력 version을 주입할 함수 인자는 없다.
명시적인 승인, 현재 입력·Source·문항, 권한 revision, 유효기간, positive/new decision version을 검사한다.
서로 다른 message/decision ID와 canonical body를 생성해 outbox와 함께 확정한다.

생성기는 원본 schema 파일과 그 SHA-256을 명시적으로 요구한다. 누락·변조·알 수 없는 필드·외부 schema ref는 차단한다.
현재 합성 context/policy adapter만 제공했다. **실제 인증된 W1 context 획득 방식과 원본 schema가 미확정이므로 runtime 준비 완료는 보류**다.
기존 `core_decision.py`의 과거 중첩 제안 규격은 기존 증거 재현용으로 보존했다.

## D06. durable outbox

[question_core_outbox.py](../epick_w4/question_core_outbox.py).

파일 기반 SQLite DB의 결정 row와 outbound row를 `BEGIN IMMEDIATE` 한 경계에서 저장한다.
WAL/FULL, 고유 키, immutable trigger, 영속 attempt/error/시각, lease를 사용한다.
보낼 때마다 새 메시지를 만들지 않으며, 성공적인 transport acceptance 뒤에만 `sent`로 바꾼다.
불확실한 응답은 `prepared`로 유지해 같은 본문을 재시도한다. 철회 등으로 `blocked`된 제출은 자동 부활하지 않는다.

**현재 검증은 실제 로컬 SQLite + 실제 프로세스 강제 종료/재시작 + 모의 queue**다.
DB commit 후 종료, 모의 acceptance 후 종료, 응답 유실, 동시 제출, lease 재획득과 오래된 worker 차단을 검사했다.
이는 실제 AWS/PostgreSQL 공동 검증을 대체하지 않는다.

## D07. currentness relay / IAM

[question_core_relay.py](../epick_w4/question_core_relay.py).

매 claim/retry 후 W1 context와 W4 policy를 다시 조회하고 권한·유효기간·문항·Source·입력·결정 버전·policy revision을 대조한다.
전송 직전 lease 소유권도 확인한다. SDK 내부 재시도는 꺼서 재전송이 반드시 이 경로를 다시 거친다.
실제 SQS adapter는 default disabled이며 W1_ADOPTED provenance, schema SHA, 고정 main queue URL/ARN/region 설정이 필요하다.
기존 TEST_ONLY schema를 상태 문자열만 바꿔도 전송할 수 없다.

운영 role은 **W4 main queue의 `sqs:SendMessage`만** 부여해야 한다. DLQ send, receive/delete/purge, W1 DB 쓰기는 요구하지 않는다.
코드에 receive/delete/purge 함수가 없다는 검사와 실제 IAM enforcement 검증은 다르다. **실제 principal/IAM 검증은 미실행**이다.
[실행 구성 이름과 host 연결 안내](w4-question-core-producer.md)를 참고한다.

## D08. 재현·접근 가능한 pin

```text
W4 repository: https://github.com/Team-1AM-Club/Project_EPICK_Engine
W4 producer/outbox accessible full SHA: PENDING — 이번 변경은 로컬 미커밋
Local branch: feat/w4-recommendation-pipeline
Local base: d9e31822e2a031b41a303f05ad1e96d29fa09d8f (이번 producer 미포함)
Canonical schema: PENDING_W1_ORIGINAL
Local test schema/fixtures: samples/question-core-local/
Producer codec: epick_w4/question_core_contract.py, epick_w4/question_core_producer.py
Outbox: epick_w4/question_core_outbox.py
Relay: epick_w4/question_core_relay.py
Python: 3.12.14
SDK: boto3 1.43.97 / botocore 1.43.97
```

저장소 루트에서:

```powershell
uv sync --locked --extra api --extra test
uv run --locked --extra api --extra test python scripts/verify-question-core-producer.py --output-dir output/question-core-check-new
uv run --locked --extra api --extra test python scripts/verify_service_handoff.py --output-dir output/question-core-full-new
```

각 출력 경로는 새 폴더여야 한다. 전용 producer 검사는 **59개 통과, 실패/오류/skip 0**이며,
별도 프로세스 종료/복구 시연도 통과했다. [이번 상세 결과](../output/question-core-producer-20260919/local/summary.json).
신규 59개를 포함한 **전체 440개도 통과, 실패/오류/skip 0**이다. 기존 가상 HTTP 시연 2개도 통과했다.
전체 회귀 결과는 [전체 검증 기록](../output/question-core-producer-20260919/full/summary.json)에 분리했다.
원격 CI 실행·push·배포·LLM 호출은 하지 않았다.

최초 44개 검사에서는 테스트 코드가 조회용 SQLite 연결을 닫지 않아 Windows 정리 단계 오류 11개가 발생했다.
명시적인 close로 수정했고 최종 검사에서 재현되지 않았다. runtime 연결 관리 코드는 처음부터 close/rollback을 수행했다.

## D09. 공동 CT-12

상태: **NOT_RUN**. W4 실행 담당은 W4 담당자, 제품 승인 담당자는 아직 지정되지 않았다.
가능 milestone은 날짜 대신 다음 조건으로 정의한다.

1. W1 원본 채택표/schema/full SHA 확보, 양측 항목별 합의와 동일 fixture/digest suite 통과.
2. 실제 W1 context 인증/currentness adapter, 제품 승인, W4 main queue send-only identity와 영속 DB volume 준비.
3. W1/W4 접근 가능한 구현 full SHA, immutable producer image digest, 정본 runbook과 격리 DB/queue·정리 책임 확정.
4. 그 뒤 요청서 D09의 10개 시나리오를 실제 producer로 공동 실행. row count, 명령·결과, teardown까지 기록.

현재 W4 image digest, isolated DB/queue 식별자, 실제 SQS acceptance, W1 logical-once receipt·DB commit/queue-delete crash는 제공하지 못한다.
W1 합성 sender만의 결과나 이번 로컬 검사를 CT-12로 제출하지 않는다.

## D10. 미완료와 인계 조건

| 항목 | 상태 | 담당 | blocker | 준비 완료 기준 / milestone |
| --- | --- | --- | --- | --- |
| 계약 채택 | W4 항목별 회신 초안 | W1/W4 | 원본 2개 미확보 | 원본 A1에 이 회신 대응, schema revision과 합의 기록 확정 |
| P1–P3 승인 | P1 수용, P2/P3 운영 보류 | W4·제품 승인자 미지정 | 운영 의미 정책 승인 없음 | 승인 담당자·사례·정책 revision 확정 후 REAL 활성화 별도 검토 |
| producer codec | 로컬 구현·검증 완료 / 운영 보류 | W4, context 제공 W1 | 원본 schema·인증 context 경계 없음 | adopted schema + authenticated adapter로 양측 계약 검사 |
| durable outbox | SQLite 구현·재시작 로컬 검사 완료 | W4 | 실제 배포 영속 volume·전송 환경 없음 | 배포 storage 설정과 실제 SQS crash window 검증 |
| relay/IAM | adapter·currentness 로컬 검사 완료 | W4, identity/queue 제공 측 | 실제 principal/queue 미제공 | 최소 권한 실측과 격리 환경 실행 |
| accessible full SHA | 미커밋·미푸시 | W4 | 현재 범위는 로컬 구현·검증 | 검토된 전달 범위를 commit/push한 뒤 독립 checkout 검증 |
| joint CT-12 | 미실행 | W1/W4, W2 경계 협조 | 위 조건·runbook·image digest 없음 | D09 전 시나리오 및 teardown 통과 |

**현재 W1 T004·Phase 2, W1_W4_CT12_COMPLETE, W2_HANDOFF_READY의 해제 근거로 사용할 수 없다.**
W1에 우선 요청하는 것은 위 원본 2개와 포함된 full SHA, 실제 context 전달 경계다.
