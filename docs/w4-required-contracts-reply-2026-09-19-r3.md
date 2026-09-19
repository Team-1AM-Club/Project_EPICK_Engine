# W4 → W1 후보 원문 검토 회신 r3

현재 제출 형식은 [필수 A–F 회신 r3.1](w4-mandatory-r3-reply-2026-09-19.md)이다. 아래는 직전 r3의 상세 검토·실행 기록이며 당시 수치를 보존한다.

작성일: 2026-09-19. 대상: [후보 원문 전달서](inputs/W1_W4_Candidate_Contract_Source_2026-09-19.md).
상태: **CANDIDATE_SOURCE_VERIFIED / W4_TECHNICAL_ACCEPTANCE_DRAFT / PRODUCTION_DISABLED**.
W4의 항목별 검토 회신 초안이다. 외부 발송·양측 합의·제품 승인·정식 채택 commit은 아직 없다.
[이전 r2](w4-required-contracts-reply-2026-09-19-r2.md)의 후보 원문 미수령 상태는 이번 전달로 해소됐다.

## 원문 확인과 완료 범위

§6·§7의 fenced block을 공백·줄바꿈을 바꾸지 않고 추출했다. 두 SHA-256이 전달서와 정확히 일치했다.

| 원문 | 검증 SHA-256 |
| --- | --- |
| [w4-adoption.md](../samples/question-core-candidate-20260919/upstream/w4-adoption.md) | 6b4bfe3b0796c376b9b5f2831e66aaf526c3f27f94e80f5112f2df0d559b537f |
| [wire schema](../samples/question-core-candidate-20260919/upstream/w4-question-core-decision.event.schema.json) | 1eb0506d9b13e22198ea11fb5fccd628096de2903b0fe5b1da3d383928d8407a |

[전달 출처·팀 보고 상태](../samples/question-core-candidate-20260919/source-provenance.json).
후보 원문을 다시 요청할 필요가 없다. 두 파일은 검토용이며 후보 commit SHA는 없다.
bb27a692cf002100a3f773df7e434e90fe03f83f는 기존 W1 기준,
41dd0c21692c7f59c87962cf1e7d2746bac73303은 adoption 문서의 역사적 작성 기준이다.
둘 다 후보 flat schema 채택 commit을 뜻하지 않는다.

첨부 상태 이미지에서 W1 단독 구현·AWS 기본 설정 완료를 보고받았다.
이를 **팀 보고**로 기록하며 실제 W4 sender identity·queue 연결·W1 인증 context·공동 CT-12를 검증한 것으로 표시하지 않는다.
이 전달본은 W4 검토·코드·로컬 검증 자료다.

## 원문 §4 양식: D01–D03 항목별 회신

아래 상태의 채택은 W4의 기술적 수용 입장이다. 양측 채택 완료·실제 데이터 활성화와 구분한다.

| 항목 | 상태 | 근거 파일·테스트 | 요청 변경 또는 blocker |
| --- | --- | --- | --- |
| A1 schema/flat event | **채택** | 후보의 18개 필수 필드, additionalProperties=false, version/type, null company와 조건을 원문 그대로 검증. candidate 전용 fixture·테스트 제공. | 원문 수정 요구 없음. 0.1-candidate는 검토 전용이며 운영 버전·채택 pin은 합의 후 확정. |
| A1 explicit job_id / no inference | **채택** | producer.prepare는 submission/context key만 받고 trusted W1ContextPort에서 job_id 조회. 다른 유효 UUID도 context와 다르면 거부. | 실제 인증 context 공급 계약·adapter 연결 필요. 최근 Job·question/source 조합 추정 금지. |
| A1 stable IDs/body retry | **채택** | 서로 다른 message_id/decision_id 생성·영속화. 같은 제출에서 occurred_at/body/digest 불변. 10회 모의 응답 유실 재시도·실제 프로세스 복구 검사. | 실제 SQS acceptance·W1 logical-once는 공동 CT-12에서 확인. |
| A1 null company / no hints | **채택** | company_id는 null, owner/project/company hint·중첩 payload 미전송. current Job 관계는 W1 담당. | W4 codec이 type:null도 읽도록 수정. 후보 schema 원문 수정 없음. |
| A1 dedicated auth/queue | **채택** | W4 main queue SendMessage만 사용하는 adapter, default disabled. body producer는 인증으로 사용 안 함. W3 worker 재사용 안 함. | W4 실제 role/SenderId와 W1 expected sender·전용 queue 연결 확인 필요. |
| P1 | **채택** | W4PolicyPort의 명시적 승인 판단만 사용. LLM SUPPORTED·경험 우선순위·W3 USABLE을 자동 Core로 변환하지 않음. | 운영 context/policy adapter도 이 경계를 유지해야 함. |
| P2 | **보류** | W4는 필수 CORE_REQUIRED / 보완 NON_CORE_OPTIONAL / 불명확 미발행 원칙을 합성 사례에서 수용. | 운영 판단 기준·제품 승인자 미지정. 담당 지정·검토 사례·policy revision 승인 후 활성화 검토. |
| P3 | **보류** | 합성 policy는 QUESTION_EVIDENCE_REQUIRED / SUPPLEMENTARY_CONTEXT의 정확한 쌍만 허용. 원문·개인정보를 reason에 넣지 않음. | 후보 wire의 reason grammar는 더 넓다. 정책 승인자·허용 reason 의미 확정 필요. |
| T1 | **채택** | W4 의미 판단·trusted Job·stable ID/body·durable outbox·발행 직전 검사·send-only relay. 코드와 로컬 증거 제공. | 실제 context/영속 volume/identity/배포 image 준비 전 actual runtime ready는 보류. |
| T2 | **채택** | W1 transport 인증, Job/owner/project/question/Source/input/epoch/fence, 원자 receipt/decision/binding, user retry와 W2 실행 경계 소유. | W1 구현·AWS 완료는 팀 보고. 공동 실측은 아직 없음. |
| T3 | **채택** | W2는 W1 승인 command·protected lookup·commit gate 사용. W4 receipt를 수집 완료로 해석하지 않음. | W2의 실제 실행 검증은 W1/W2 담당, W4가 대신 완료 선언 안 함. |
| T4 | **채택** | W3 지식/usability와 W4 판단·W2 ACK의 계약을 각각 유지. | 다른 팀 계약 변경 요구 없음. |
| T5 | **채택** | W4 receipt는 Job을 WAITING_USER에 유지. 명시적 user retry만 새 fence/W2 command 생성. 새 W1→W4 ACK API/event 추가 안 함. | 실제 Job 상태·command 0건/생성 시점은 W1/W2와 CT-12에서 검사. |

P2/P3의 의미 정책 책임은 W4, 운영 승인 책임은 팀이 지정할 제품/정책 승인자다.
승인자 실명을 추정하지 않았다. 승인 milestone은 담당 지정 → 검토 사례·정책 revision 승인 → 활성화 검토다.
REAL 자료 준비·발행과 후보 버전의 실제 SQS 전송은 코드에서 계속 차단한다.
원문의 Phase 2 기준은 미승인 정책을 enablement blocker로 기록하고 producer SHA 미완료 시 milestone을 기록하는 경로도 허용한다.
따라서 W1이 이 회신을 검토해 자체 진행 여부를 판단할 수 있다. W4가 W1 Phase 2나 T004 완료를 대신 선언하지 않는다.

## 구현 대조와 수정

| 항목 | 후보 원문 | W4 반영·호환성 영향 |
| --- | --- | --- |
| company_id | type:null | 기존 codec의 const:null 요구 때문에 CORE_SCHEMA_UNSUPPORTED 재현. type:null을 동일한 null 고정값으로 읽도록 수정. nullable string이나 arbitrary company는 여전히 거부. |
| schema_version / message_type | w4.private.question-core-decision/0.1-candidate / w4.private.w1.question-core-decision | 원문 값을 읽어 생성. 예전 TEST_ONLY fixture는 역사적 검사로 보존. 후보 전용 예제·검증 경로 추가. |
| reason_code | 대문자 시작, 대문자·숫자·밑줄 최대64자 | wire grammar를 그대로 수용. FUTURE_REASON은 schema상 유효하나 현 policy에서는 거부. schema 유효성과 정책 승인을 구분하는 fixture 제공. |
| provenance / 전송 | 검토 후보, adopted 아님 | W1_CANDIDATE 상태 추가. 후보 버전은 W1_ADOPTED로 이름만 바꿔도 SDK 생성 전에 실제 전송 거부. |
| body 크기·digest | 후보 schema에는 전체 byte 상한·digest 필드 없음 | W4 로컬 상한16KiB, canonical JSON·digest vector는 별도 제안. 새 wire 필드를 추가하지 않음. 양측 값·계산 규칙 합의 필요. |

W1 원문 수정 요청은 없으므로 schema diff/patch는 없다. 변경은 W4 codec 호환 처리와 로컬 검증 경로다.
생성된 [Core](../samples/question-core-candidate-20260919/core-required.json)와
[Non-Core](../samples/question-core-candidate-20260919/non-core-optional.json)가 수정하지 않은 후보 schema를 통과한다.

## D04–D07 산출물

- [후보 schema·원문·fixture manifest](../samples/question-core-candidate-20260919/manifest.json).
- [거부/결속 fixture 25개](../samples/question-core-candidate-20260919/negative-events.json): codec 거부21개와 context 결속4개. 각 schema_valid를 별도로 기록. 같은 ID·3.0 revision 등 schema가 허용해도 codec이 더 엄격한 경우를 숨기지 않음.
- [정책 경계 사례](../samples/question-core-candidate-20260919/policy-boundary.json), [digest vector 3개](../samples/question-core-candidate-20260919/digest-vectors.json). 기존 generic W1 helper와 일치, 새 consumer의 합의·검증은 아님.
- [codec](../epick_w4/question_core_contract.py), [producer](../epick_w4/question_core_producer.py), [outbox](../epick_w4/question_core_outbox.py), [relay](../epick_w4/question_core_relay.py).
- [후보 전용 테스트](../tests/test_question_core_candidate.py), [공통 producer 검사](../tests/test_question_core_producer.py), [SQS Stubber 검사](../tests/test_question_core_sqs.py).
- [실행·host 구성 안내](w4-question-core-producer.md).

SQLite 영속 저장·프로세스 종료/복구는 실제 로컬 실행이며 queue/context/policy는 합성이다.
W1 DB 쓰기·수신·삭제 권한이나 실제 사용자 원문을 요구하지 않는다.

## 원문의 추가 회신 필드 / D08

| 필드 | 회신 |
| --- | --- |
| W4 repository/access path | https://github.com/Team-1AM-Club/Project_EPICK_Engine |
| W4 producer/outbox full SHA | **PENDING**. 로컬 변경이며 접근 가능한 신규 commit 없음. base d9e31822e2a031b41a303f05ad1e96d29fa09d8f는 producer 미포함. |
| Schema path | samples/question-core-candidate-20260919/upstream/w4-question-core-decision.event.schema.json — 검토 후보, adopted 아님 |
| Valid / negative fixture | 같은 폴더 core-required.json, non-core-optional.json, negative-events.json, policy-boundary.json |
| Codec/currentness 검사 | 아래 producer 명령. 정확한 결과는 이번 local/summary.json 참조 |
| Outbox/restart 검사 | 동일 명령이 후보 버전으로 별도 프로세스 종료·복구 시연도 실행 |
| Safe env var names | W4_CORE_OUTBOX_PATH, W4_CORE_SCHEMA_PATH, W4_CORE_SCHEMA_SHA256, W4_CORE_W1_FULL_SHA, W4_CORE_MAIN_QUEUE_URL, W4_CORE_MAIN_QUEUE_ARN, AWS_REGION, W4_CORE_SEND_ENABLED |
| Joint CT-12 owner/contact | W4 담당자 실행, W1/W2 경계 담당자와 일정은 팀 지정 필요 |
| Earliest milestone | 양측 합의·미승인 policy 제한 기록, source pin/image, 실제 인증 context·전용 queue/identity·격리 환경·runbook 준비 뒤 |

producer/outbox의 완료 owner는 W4다. actual runtime 전달 조건은 합의된 version/schema/fixture/codec,
실제 W1 context adapter, 영속 volume과 send-only identity를 연결한 image, 접근 가능한 full SHA다.
후보 검토 뒤 양측이 합의한 내용을 commit/push·SHA 교환한다. ZIP은 full SHA를 대신하지 않는다.

## 실행과 결과

저장소 루트에서 새 출력 폴더로 실행한다.

~~~powershell
uv sync --locked --extra api --extra test
uv run --locked --extra api --extra test python scripts/prepare-question-core-candidate-fixtures.py
uv run --locked --extra api --extra test python scripts/verify-question-core-producer.py --contract w1-candidate --output-dir output/candidate-local-new
uv run --locked --extra api --extra test python scripts/verify_service_handoff.py --output-dir output/candidate-full-new
~~~

[이번 후보·producer 검사](../output/question-core-candidate-20260919/local/summary.json) ·
[이번 전체 검사](../output/question-core-candidate-20260919/full/summary.json) ·
[파일별 전달 안내](w4-question-core-candidate-handoff-2026-09-19.md).
이번 실행은 producer73개와 전체454개 모두 통과했고 실패·오류·skip0이다. 후보 프로세스 복구 시연과 가상 HTTP2개도 통과했다.
실제 queue/LLM 호출·W1 공동 계약 suite·PostgreSQL 검증은 하지 않았다.

## D09–D10 남은 조건

1. W1의 D01–D03 항목별 수용·이견 회신. P2/P3 승인자·enablement 조건 지정.
2. 후보에서 정식 운영 version, body 상한·canonical digest/fixture를 확정하고 양측 source pin 교환.
3. 실제 W1 인증 context adapter, W4 main queue·role/SenderId·W1 expected sender 결속, 영속 volume·image digest 준비.
4. [공동 CT-12 준비표](w4-question-core-ct12-runbook-draft.md)의 10개 시나리오와 teardown 실행.

W1 AWS 기본 설정이 완료됐다는 보고와 W4 실제 연결·공동 CT-12 완료는 구분한다.
현재 W1_W4_CT12_COMPLETE와 W2_HANDOFF_READY는 선언하지 않는다.
