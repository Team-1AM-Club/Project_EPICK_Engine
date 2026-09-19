# W4 → W1 계약 합의 전 항목별 회신 r2

> 이전 기록이다. 후보 원문 수령·검증 후 [r3 회신](w4-required-contracts-reply-2026-09-19-r3.md)으로 갱신했다. 아래 원문 미수령 상태는 당시 기록이다.

작성일: 2026-09-19. 대상: [9월 19일 전달 요청서](inputs/W1_W4_Required_Contracts_2026-09-19.md).
상태: **PRE_ADOPTION_REPLY_READY / LOCAL_PRODUCER_VERIFIED / CANDIDATE_ORIGINAL_PENDING**.
W4의 회신 초안이며 외부 발송·양측 합의·제품 승인을 마치지 않았다.
[이전 회신](w4-required-contracts-reply-2026-09-19.md)의 선행 순서를 아래와 같이 정정한다.

## §0. 검토 기준과 합의 순서

| 항목 | W4 입장 | 확인 근거·적용 |
| --- | --- | --- |
| 후보 검토 → D01–D03 합의 → 채택본 SHA 교환 | **채택** | 채택 완료 SHA를 후보 검토의 선행 조건으로 요구하지 않는다. |
| 기존 기준 `bb27a692cf002100a3f773df7e434e90fe03f83f` | **검토 기준으로 채택** | 기존 schema 2개·fixture 1개의 Git 원본 SHA-256이 요청서와 일치했다. W4 flat 계약의 채택 커밋은 아니다. |
| 후보 schema·A1 원문 | **수령 대기** | 요청서에 경로·review SHA만 있다. 기준 커밋에도 두 원문이 없다. 미커밋 검토 파일로 제공해도 된다. |
| 실제 자료·consumer 연결 | **합의·승인 전 비활성** | 합성 검증만 계속하며 REAL 생성·발행 제한을 유지한다. |

[검증 기록](../samples/question-core-review-20260919/source-review.json): 원본 체크섬 **3/3**,
기존 계약의 호환·거부 조건 **11/11** 통과. W1 consumer suite·실제 전송 검사는 아니다.
기존 기준은 `channel`과 `payload`가 있는 중첩 envelope이며 payload에 `job_id`가 없다.
기존 payload에 job_id를 추가하거나 W4 TEST_ONLY flat event를 넣으면 schema가 거부한다.
이것은 예상된 형식 차이이며, 기존 fixture를 후보 flat 규격으로 승격하지 않는다.
새 `decision_owner=W4` wire 필드 역시 기존 payload에 있다고 기록하지 않는다.

| 필요한 후보 원문 | 요청서의 review SHA-256 — 원문 바이트와 아직 미대조 |
| --- | --- |
| `specs/004-w1-w4-question-core/w4-adoption.md` | `6b4bfe3b0796c376b9b5f2831e66aaf526c3f27f94e80f5112f2df0d559b537f` |
| `specs/004-w1-w4-question-core/contracts/w4-question-core-decision.event.schema.json` | `1eb0506d9b13e22198ea11fb5fccd628096de2903b0fe5b1da3d383928d8407a` |

## D01. 계약 8개 항목

요청서에 명시된 항목에 대한 W4 입장이다. 원문 A1 전체를 확인·작성했다는 뜻은 아니다.

| 항목 | W4 회신 | 근거·남은 조건 |
| --- | --- | --- |
| 1. flat event / schema version | **flat 채택 / 정확한 version·제약 보류** | 후보 원문으로 constants·필수 필드·길이·reason·canonicalization 대조. 채택 완료 SHA는 이후 교환. |
| 2. W1-issued job_id | **채택** | trusted host의 W1ContextPort에서만 받는다. client·LLM의 Job 추정·주입 금지. 실제 인증 context 경계는 합의 필요. |
| 3. message_id / decision_id 분리 | **채택** | 서로 다른 UUID를 최초 준비 때 생성·저장하고 동일 제출 재시도에 재사용한다. |
| 4. scope / owner / producer 고정 | **채택** | QUESTION_MATCHING / W4 / w4. producer 문자열은 인증을 대신하지 않는다. |
| 5. company_id=null | **채택** | 문항 pin은 null 유지. 수집 회사·소유 관계는 W1이 현재 관계로 검증한다. |
| 6. owner/project/company hint 제외 | **채택** | wire에서 제외한다. W1 authorization_revision은 관계·권한·epoch/fence 변경을 반영해야 한다. |
| 7. 전용 queue/principal | **채택** | W4 main queue send-only. W3 경로·DLQ send·W1 receive/delete/purge·DB 쓰기 사용 안 함. 실제 환경 검증 대기. |
| 8. 불변 재시도 | **채택** | ID·발생 시각·canonical body·digest를 영속화한다. 실제 프로세스 종료·복구와 모의 응답 유실 검사 완료. |

후보 원문에서 이견을 발견하면 field/형식/의미/fixture/호환성 영향을 명시한다.
현재 TEST_ONLY version과 16 KiB 제한은 합의된 W1 값이 아니다.

## D02. P1–P3 의미 정책

| ID | W4 입장 | 담당·근거 | 활성화 조건 / milestone |
| --- | --- | --- | --- |
| P1 | **채택** | W4. host 승인 문항/Source만 판단. LLM SUPPORTED·경험 순위·C01 USABLE을 자동 Core로 변환하지 않음. | 신뢰된 context·명시적 policy 공급 유지. |
| P2 | **합성 검증안 채택 / 운영 승인 보류** | W4 의미 정책, 제품 승인자 팀 지정 필요. 필수 CORE_REQUIRED, 보완 NON_CORE_OPTIONAL, 불명확하면 발행 보류. | 승인자·검토 사례·판단 기준·policy revision 확정 후 운영 활성화 별도 검토. |
| P3 | **후보 reason 수용 / 운영 승인 보류** | W4. 필수 QUESTION_EVIDENCE_REQUIRED, 보완 SUPPLEMENTARY_CONTEXT. 원문·개인정보 제외. | 후보 schema reason 대조 및 제품 승인. |

W1의 단독 정책 승인을 요구하지 않는다. 합성 fixture의 approved=true는 제품 승인 증거가 아니다.
REAL 제한은 승인만으로 자동 해제되지 않는다.

## D03. T1–T5 책임

| ID | W4 회신 | 책임 경계·미해결 사항 |
| --- | --- | --- |
| T1 | **채택** | W4 의미 판단·trusted Job·불변 메시지·durable outbox·전송 직전 검사·send-only relay. 실제 context adapter는 W1 경계 확정 후 연결. |
| T2 | **채택** | W1 transport 인증·현재 관계/input/epoch/fence 검사·receipt/decision/binding 원자 저장·user retry·W2 실행. |
| T3 | **채택** | W2는 W1 command·protected lookup만 소비. W4 receipt는 수집 완료가 아님. W2의 수용 확인은 별도 필요. |
| T4 | **채택** | W3 지식/usability, W4 inbound, W2 ACK는 각각 계약 유지. |
| T5 | **채택** | receipt만으로 W2 실행 재개 금지. 명시적 사용자 retry가 새 fence·W2 command 생성. |

위 표는 W4 입장이며 상대 팀의 회신·합의를 대신 기록하지 않는다.

## D04. schema·fixture·digest

정식 flat schema 채택과 양측 공통 contract suite는 대기 상태다.

- [TEST_ONLY schema](../samples/question-core-local/test-only.schema.json): 후보 원본이 아니며 실제 SQS adapter가 거부한다.
- [Core](../samples/question-core-local/core-required.json) / [Non-Core](../samples/question-core-local/non-core-optional.json): 합성 정상 fixture.
- [거부 fixture 22개](../samples/question-core-local/negative-events.json), [digest vector 3개](../samples/question-core-local/digest-vectors.json), [체크섬](../samples/question-core-local/manifest.json).
- stale/same revision·exact retry 10회·동일 ID/다른 body·동일 decision ID/다른 message는 [테스트](../tests/test_question_core_producer.py)에서 검증한다.
- [기존 W1 원본과 출처](../samples/question-core-review-20260919/source-review.json)는 compatibility 검토용이다.

기존 generic W1 digest helper와의 일치는 004 consumer 검증을 대신하지 않는다.
후보 검토·합의 후 양측 schema/fixture/codec을 반영하고 같은 검사를 실행한다.

## D05–D07. producer / outbox / relay

| 항목 | 코드 | 현재 범위 |
| --- | --- | --- |
| D05 | [codec](../epick_w4/question_core_contract.py), [producer](../epick_w4/question_core_producer.py) | trusted host context·policy, Job/문항/Source/input/revision 결속. 실제 인증 adapter·후보 schema 대조 대기. |
| D06 | [outbox](../epick_w4/question_core_outbox.py) | 실제 SQLite 단일 transaction, 불변 저장, lease, 재시작·응답 유실 검사. queue는 모의 구현. |
| D07 | [relay](../epick_w4/question_core_relay.py) | 매 발행 직전 currentness·policy·lease 검사. boto3 호출은 Stubber 검증. 실제 SQS/IAM 미실행. |

DB는 단일 host의 영속 로컬 volume을 사용한다. 동작 중인 DB를 Google Drive로 두 PC가 공유하지 않는다.
전송 성공은 transport acceptance만 뜻하며 W1 적용·W2 실행·사용자 공개를 보장하지 않는다.

## D08. 재현과 접근 가능한 SHA

```text
Repository: https://github.com/Team-1AM-Club/Project_EPICK_Engine
Local branch: feat/w4-recommendation-pipeline
Local base: d9e31822e2a031b41a303f05ad1e96d29fa09d8f (producer 미포함)
W4 producer/outbox accessible full SHA: PENDING (로컬 미커밋)
W1 existing baseline: bb27a692cf002100a3f773df7e434e90fe03f83f
W1/W4 adopted flat schema full SHA: NOT_YET_AGREED
Python: 3.12.14
boto3 / botocore: 1.43.97 / 1.43.97
```

후보 검토·D01–D03 합의 뒤 양측 schema/fixture/codec을 commit·push하고 full SHA를 교환해 독립 재현한다.
ZIP이나 현재 base SHA가 D08 수락 기준을 대신하지 않는다.

저장소 루트에서 실행하며 출력 경로는 새 폴더여야 한다.

```powershell
uv sync --locked --extra api --extra test
uv run --locked --extra api --extra test python scripts/verify-question-core-review.py --service-reference <Service-checkout> --request-file docs/inputs/W1_W4_Required_Contracts_2026-09-19.md --output-dir output/new-review
uv run --locked --extra api --extra test python scripts/verify-question-core-producer.py --output-dir output/new-producer-check
uv run --locked --extra api --extra test python scripts/verify_service_handoff.py --output-dir output/new-full-check
```

Git이 PATH에 없으면 첫 검증에 `--git <git.exe 경로>`를 추가한다. Service checkout에 baseline 커밋이 있어야 한다.
[이번 검증·파일별 전달 안내](w4-question-core-review-handoff-2026-09-19.md).
직전 전체 440개 결과는 [기존 전체 검증](../output/question-core-producer-20260919/full/summary.json)에 보존했다.
원격 CI·배포·실제 모델 품질 결과가 아니다.

설정 이름: W4_CORE_OUTBOX_PATH, W4_CORE_SCHEMA_PATH, W4_CORE_SCHEMA_SHA256, W4_CORE_W1_FULL_SHA,
W4_CORE_MAIN_QUEUE_URL, W4_CORE_MAIN_QUEUE_ARN, AWS_REGION, W4_CORE_SEND_ENABLED(기본 false).
이는 host 연결용 이름이며 환경 변수만으로 실행되는 서버를 제공한 것은 아니다.
[host 구성 안내](w4-question-core-producer.md)를 따른다.

## D09. 공동 CT-12

**NOT_RUN**. [공동 검증 준비표](w4-question-core-ct12-runbook-draft.md)에 10개 시나리오·담당·증거를 정리했다.
W4는 producer/outbox/relay, W1은 인증 context·consumer·격리 DB/queue·취소/삭제/retry,
W2는 command/relay/lookup 경계에 참여한다. 담당자 실명·일정·image digest는 미제공이므로 만들지 않았다.
milestone은 D01–D03 합의·양측 pin·실제 context·격리 환경·teardown 책임 확정 후다.

## D10. 미완료와 인계 조건

| 항목 | 상태 | 담당 | blocker / 준비 완료 기준·milestone |
| --- | --- | --- | --- |
| 후보 원문 | 경로·checksum만 확보 | W1 제공/W4 검토 | 원문 2개 바이트 수령·대조 후 정확한 A1 양식에 회신 반영 |
| D01 계약 | 8개 항목 W4 입장 준비 | W1/W4 | version·제약 대조·이견 해소·양측 합의 기록 |
| P1–P3 승인 | P1 수용, P2/P3 운영 보류 | W4·제품 승인자 미지정 | 승인자·사례·policy revision·활성화 조건 확정 |
| T1–T5 | W4 수용 입장 준비 | W1/W4, W2/W3 확인 | 상대 팀 회신·책임별 이견 해결 |
| 정식 schema/fixture/codec | TEST_ONLY 검사 | W1/W4 | 위 합의 후 반영·양측 공통 suite 통과 |
| 실제 producer | 로컬 구현·검사 완료 | W4/context 제공 W1 | 인증 context 계약·adapter 연결 |
| durable outbox | SQLite 복구 검사 완료 | W4 | 배포 volume·실제 transport crash window 검사 |
| relay/IAM | adapter 로컬 검사 완료 | W4·환경 제공 측 | main queue/principal 준비·최소 권한 실측 |
| full SHA | 미커밋·미푸시 | W1/W4 | 합의본 commit/push·독립 재현 |
| joint CT-12 | 준비표 작성, 미실행 | W1/W4/W2 | source pin·image·격리 환경·전 시나리오·teardown 통과 |

현재 결과는 W1 T004/Phase 2, W1_W4_CT12_COMPLETE, W2_HANDOFF_READY 해제 근거가 아니다.
우선 요청은 **채택 전 후보 원문 2개, D01–D03 회신과 정책 승인자 지정**이다. 채택 완료 SHA는 합의 뒤 교환한다.
