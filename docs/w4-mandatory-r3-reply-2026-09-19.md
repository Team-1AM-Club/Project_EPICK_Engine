# W1 필수 양식을 반영한 W4 r3 회신 · r3.1

이 문서는 당시 회신이다. 현재 후속은 [실제 runtime 회신 r4](w4-actual-runtime-handoff-reply-2026-09-19.md)다.

작성일: 2026-09-19. [이번 필수 양식](inputs/W1_W4_Mandatory_R3_Reply_Format_2026-09-19.md) §4의 전체 구조와 요구 문구를 유지하고 모든 칸을 기입했다.
W1이 인용한 r2 이후 후보 원문 수령·byte 검증과 codec 수정은 완료했다. 이번 r3.1은 [직전 r3](w4-required-contracts-reply-2026-09-19-r3.md)의 증거를 정확한 필수 형식으로 정리한 후속 회신이다.
**미발송 W4 회신**이며 W1·W2·W3의 동의, 운영 정책 승인, 실제 전송 또는 공동 CT-12 완료를 선언하지 않는다.
아래 `채택`은 W4의 기술적 수용 입장이다. 모든 경로는 압축을 푼 Engine 루트 기준이다.

```text
# W4 → W1 Question Core pre-adoption r3 회신

상태: PENDING — 필수 양식 기입 완료 / W4 기술 검토 완료 / 양측 합의·정책 승인·공유 commit·실제 연결 대기
W4 review artifact version: w4-question-core-pre-adoption-r3.1-20260919 (W1 필수 r3 형식 보완본)
W4 repository/access path: https://github.com/Team-1AM-Club/Project_EPICK_Engine ; 첨부 ZIP은 로컬 변경 사본이며 저장소에 게시된 producer commit이 아님
W4 current local base SHA: d9e31822e2a031b41a303f05ad1e96d29fa09d8f (새 producer/outbox 변경 미포함)
W4 producer/outbox accessible full SHA: PENDING (로컬 미커밋 변경; 신규 push 없음)

## A. 후보 원문 byte 수령 및 대조

candidate_originals_received: 2

| 후보 | 수령한 문서/section | 계산한 SHA-256 | W1 제공 SHA-256 | byte_verified |
| --- | --- | --- | --- | --- |
| w4-adoption.md | docs/inputs/W1_W4_Candidate_Contract_Source_2026-09-19.md §6 원문 fenced block; 추출본 samples/question-core-candidate-20260919/upstream/w4-adoption.md | 6b4bfe3b0796c376b9b5f2831e66aaf526c3f27f94e80f5112f2df0d559b537f | 6b4bfe3b0796c376b9b5f2831e66aaf526c3f27f94e80f5112f2df0d559b537f | true |
| w4-question-core-decision.event.schema.json | docs/inputs/W1_W4_Candidate_Contract_Source_2026-09-19.md §7 원문 fenced block; 추출본 samples/question-core-candidate-20260919/upstream/w4-question-core-decision.event.schema.json | 1eb0506d9b13e22198ea11fb5fccd628096de2903b0fe5b1da3d383928d8407a | 1eb0506d9b13e22198ea11fb5fccd628096de2903b0fe5b1da3d383928d8407a | true |

원문 byte가 일치하지 않으면: NONE

## B. D01 wire 계약 — 후보 원문 기준의 최종 항목별 판정

| ID | 후보 요구 | 상태 (채택/수정/보류) | W4 근거·코드/테스트 경로 | 수정안 또는 blocker |
| --- | --- | --- | --- | --- |
| D01-01 | flat event 및 `schema_version=w4.private.question-core-decision/0.1-candidate`, `message_type=w4.private.w1.question-core-decision`, `visibility_scope=PRIVATE` | 채택 | samples/question-core-candidate-20260919/upstream/w4-question-core-decision.event.schema.json; epick_w4/question_core_contract.py; tests/test_question_core_candidate.py::test_actual_producer_uses_received_candidate_without_schema_changes — 원문 flat 18개 필수 field·version/type/visibility 상수를 그대로 사용 | 후보 원문 수정 요청 NONE. candidate version의 실제 전송은 계속 차단; adopted version·pin은 양측 합의 후 확정 |
| D01-02 | W1-issued `job_id` 필수, Job 추정 및 public/client/LLM 주입 금지 | 채택 | epick_w4/question_core_producer.py::QuestionCoreProducer.prepare / W1ContextPort; tests/test_question_core_producer.py::test_client_cannot_pass_job_id_to_prepare; tests/test_question_core_candidate.py::test_candidate_valid_ids_still_require_exact_context_binding — host context와 정확히 결속 | 계약 수정 요청 NONE. 실제 W1 인증 context adapter·공급 방식은 PENDING; W4 구현 / W1 인증·전달 계약 확인 필요 |
| D01-03 | `message_id`와 `decision_id` 분리, retry에서 ID·`occurred_at`·canonical body·digest 불변 | 채택 | epick_w4/question_core_outbox.py; tests/test_question_core_candidate.py::test_ten_candidate_retries_preserve_received_version_and_exact_body; output/question-core-candidate-20260919/local/summary.json restart_demo — 별도 ID와 동일 body를 영속화, 실제 프로세스 복구 통과 | 계약 수정 요청 NONE. 실제 W1 logical-once·SQS 응답 유실 경계는 공동 CT-12에서 확인; canonical digest 상호 합의는 별도 미완료 |
| D01-04 | `decision_scope=QUESTION_MATCHING`, `decision_owner=W4`, `producer=w4` 고정 | 채택 | epick_w4/question_core_contract.py; samples/question-core-candidate-20260919/core-required.json; tests/test_question_core_candidate.py::test_valid_fixtures_and_negative_matrix_separate_schema_from_codec — scope/owner/producer 고정 및 변조 거부 | NONE — body producer는 sender 인증 증거가 아님 |
| D01-05 | `company_id=null`, `question_version_id`·`source_id`·`analysis_input_version`·positive `decision_version` 포함 | 채택 | epick_w4/question_core_contract.py; epick_w4/question_core_producer.py; tests/test_question_core_candidate.py::test_supporting_type_null_does_not_allow_nullable_company_values; samples/question-core-candidate-20260919/negative-events.json — type:null 호환·필수 ID/input·양의 revision 검사 | 후보 원문 수정 요청 NONE. W4 codec의 type:null 호환 수정 완료; company 추정·hint 추가 없음 |
| D01-06 | owner/project/company hint 및 추가 field 제외, `additionalProperties=false` | 채택 | 후보 schema의 additionalProperties=false; epick_w4/question_core_contract.py; tests/test_question_core_candidate.py::test_valid_fixtures_and_negative_matrix_separate_schema_from_codec — owner/project/company hint·중첩 payload·추가 field 거부 | NONE — trusted context의 내부 정보는 wire body에 추가하지 않음 |
| D01-07 | `decision_code`와 `is_core`의 Core/Non-Core 일치, `reason_code` 형식·비민감 규칙 | 채택 | 후보 schema allOf·reason_code pattern; epick_w4/question_core_producer.py::PolicyDecision; tests/test_question_core_candidate.py::test_core_and_optional_reason_pair_remains_a_policy_check / test_candidate_reason_grammar_does_not_approve_unknown_policy — wire와 승인 policy 검사를 분리 | 후보 원문 수정 요청 NONE. wire grammar가 허용하는 다른 reason을 자동 승인하지 않음; P2/P3의 운영 승인 PENDING |
| D01-08 | W4 전용 main queue, send-only principal. body `producer`는 인증 근거가 아님 | 채택 | epick_w4/question_core_relay.py::SqsSendOnly; tests/test_question_core_sqs.py::test_only_send_message_with_exact_canonical_body / test_live_send_is_disabled_by_default — 고정 main queue SendMessage만 검사, Stubber 사용 | 계약 수정 요청 NONE. 실제 queue·role/SenderId·W1 expected sender는 PENDING; W4 배포 담당 및 W1 인증 담당 지정·연결 필요. body producer로 인증하지 않음 |

D01 수정 diff/fixture 영향: NONE — W1 후보 원문 byte 변경 없음. W4 codec의 type:null 읽기 호환만 수정. 후보 version/type의 정상2·거부/결속25·정책 경계·digest3개 fixture 제공; 기존 TEST_ONLY 자료는 역사적 검사로 보존. W4 로컬 16KiB 상한과 canonical digest 계산은 별도 상호 합의 필요하며 새 wire field를 추가하지 않음.
D01 보류 항목별 owner·해제 조건: NONE — D01-01~08의 W4 기술 판정은 모두 채택. 각 행의 실제 연결 blocker 및 C/E/F의 운영 승인·상대 팀 확인은 미해소; 양측 계약 채택 완료를 뜻하지 않음.

## C. D02 P1–P3 정책

| ID | 정책 | W4 상태 (채택/수정/보류) | 정책 승인 owner | blocker | 운영 enablement 조건 |
| --- | --- | --- | --- | --- |
| P1 | 승인된 문항/Source 근거만 판단하며 LLM SUPPORTED·경험 순위·W3 C01 USABLE을 자동 Core로 바꾸지 않음 | 채택 | W4 기술 책임: W4 담당자. 운영 정책 승인 owner: PENDING (팀 지정 필요) | W4PolicyPort는 명시적 승인 결정을 요구하나 운영 policy adapter·승인 기록 미제공. LLM SUPPORTED·경험 순위·W3 USABLE의 자동 변환 없음 | 팀 승인 owner 지정, 승인된 문항/Source 및 policy revision·검토 사례 확인, 실제 인증 context 연결과 D01–D03 합의. REAL 활성화는 별도 코드 변경·검증 필요 |
| P2 | 필수 자료=CORE_REQUIRED, 보완=NON_CORE_OPTIONAL, 불명확=발행 보류 | 보류 | W4 정책 정의·구현 책임: W4 담당자. 외부 운영 정책 승인 owner: PENDING (팀 지정 필요) | 필수/보완/불명확 원칙은 합성 사례에서 수용했으나 운영 판단 기준·검토 사례·승인자 미확정; 실제 의미 판단 policy adapter 미구현 | 승인 owner가 필수/보완/불명확 사례와 policy revision을 서면 승인하고 W4 adapter 구현·검증. 불명확은 미발행 유지; 공통 활성화 조건 충족 전 DISABLED |
| P3 | Core reason=QUESTION_EVIDENCE_REQUIRED, Non-Core reason=SUPPLEMENTARY_CONTEXT, reason에 원문/개인정보 금지 | 보류 | W4 reason 적용 책임: W4 담당자. 외부 reason 정책 승인 owner: PENDING (팀 지정 필요) | 합성 policy는 두 reason과 code의 정확한 쌍만 허용. wire의 넓은 grammar와 별개로 운영 허용 목록·의미 승인 기록 없음 | 승인 owner가 QUESTION_EVIDENCE_REQUIRED / SUPPLEMENTARY_CONTEXT 의미·허용 조합·revision 및 비민감 규칙을 승인. 원문/개인정보 금지 검사·공통 활성화 조건 충족 전 DISABLED |

현재 REAL 사용자 자료 발행 상태: DISABLED

## D. D03 T1–T5 책임 경계

| ID | 책임 | W4 상태 (채택/수정/보류) | 이견 / 상대 팀 확인 필요 사항 |
| --- | --- | --- | --- |
| T1 W4 | trusted `job_id` 보존, 의미 판단, immutable body/ID, durable outbox, send 직전 currentness 검사, send-only relay | 채택 | W4 책임으로 수용; 의미 정책·인증 context의 실제 adapter와 배포 image/영속 volume은 PENDING. 로컬 producer/outbox/relay만 검증 완료. W4 구현 담당 및 W1 context 공급 담당이 연결 계약 확인 필요 |
| T2 W1 | sender 인증, Job/owner/project/question/Source/input/epoch/fence 검사, receipt/decision/binding 원자 저장, user retry, W2 command/lookup | 채택 | W4의 책임 경계 수용 입장, W1 동의·실행 완료 대리 선언 아님. W1 담당자가 실제 sender/context/epoch/fence·원자 저장 및 retry/W2 경계 확인 필요; 공동 검증 NOT_RUN |
| T3 W2 | W1 승인 command/protected lookup만 소비. W4 receipt는 실행 완료가 아님 | 채택 | W4의 경계 수용 입장. W1/W2 담당자가 승인 command·protected lookup·commit gate 경계를 실제 확인 필요. W4 SENT/receipt는 transport 수락/수신 기록일 뿐 W2 완료가 아님 |
| T4 W3 | W3 usability와 W4 inbound/W2 ACK는 상호 대체하지 않음 | 채택 | W4의 경계 수용 입장, W3 계약 변경 요청 NONE. W1/W3 담당자가 별도 C01 처리와 W4/W2 경계 유지 확인 필요; 상대 팀 확인 기록 PENDING |
| T5 retry | W4 receipt는 재개 신호가 아니며 명시적 user retry만 새 fence/W2 command를 생성 | 채택 | W4의 경계 수용 입장. W1/W2 담당자가 receipt 후 WAITING_USER 유지·명시적 user retry 전 command 0건·retry 후 새 fence를 공동 CT-12로 검증 필요. W4에 신규 ACK/API 요구 없음 |

## E. W4 구현·인계 상태

| 영역 | 현재 상태 | 근거 경로/명령·결과 | 아직 미완료인 이유 | W4 담당 / 준비 완료 조건 |
| --- | --- | --- | --- | --- |
| candidate schema/fixture 적용 | LOCAL_VERIFIED / NOT_ADOPTED | samples/question-core-candidate-20260919/; tests/test_question_core_candidate.py 신규14개 포함 관련73개 통과; 원문2개 SHA 일치 | 후보 원문·로컬 fixture 준비 완료. 양측 채택·정식 version·공통 digest/fixture 합의 미완료 | W4 담당자 / W1과 D01–D03·최종 schema/fixture 합의 후 adopted artifact 생성·검증 |
| producer codec | LOCAL_VERIFIED | epick_w4/question_core_contract.py 및 question_core_producer.py; 후보 type:null 호환 수정; output/question-core-candidate-20260919/local/summary.json 73 PASS | 실제 문항/Source 의미 판단 policy와 W1 인증 context adapter 미구현; 로컬 합성 ports로 검증 | W4 담당자 / 합의된 인증 context·승인 policy adapter 연결·검증, REAL 제한 해제는 별도 승인·구현 필요 |
| durable outbox/restart | LOCAL_VERIFIED / REAL_SQLITE_FAKE_QUEUE | epick_w4/question_core_outbox.py; output/question-core-candidate-20260919/local/summary.json restart_demo PASSED — commit 후 종료·모의 수락 후 종료·재시작 동일 body, 임시 DB 제거 | 단일 호스트 로컬 영속 DB 범위. 배포 volume·실제 SQS 응답 유실·W1 중복 처리 공동 검증 미실행 | W4 담당자 / 영속 volume과 image 연결·재시작 확인, W1/W2와 CT-12 수행. 실행 DB를 Drive로 동시에 공유하지 않음 |
| currentness relay | LOCAL_VERIFIED / AUTHENTICATED_W1_ADAPTER_PENDING | epick_w4/question_core_producer.py::check_current; epick_w4/question_core_relay.py; 철회·만료·revision·lease 변경 테스트가 관련73개에 포함 | 실제 W1 인증 context 공급·epoch/fence 변경을 반영할 authorization_revision 전달 방식 미합의 | W4 adapter 담당 + W1 context 담당 / 인증·현재성 전달 계약 확정, 실제 취소/삭제/변경과 전송 경계 검증 |
| send-only SQS adapter | LOCAL_STUBBER_VERIFIED / ACTUAL_SEND_DISABLED | epick_w4/question_core_relay.py; tests/test_question_core_sqs.py 11개 포함 관련73개 통과; candidate version은 SDK 생성 전 거부 | 실제 W4 main queue·principal/SenderId·W1 expected sender 결속 미확인. actual SQS 요청0 | W4 배포 담당 + W1 인증 담당 (실명 PENDING) / 합의본 양측 commit·push 후 격리 queue와 SendMessage 최소 권한·sender 결속 검증 |
| accessible commit/push | PENDING / LOCAL_ONLY | 현재 branch feat/w4-recommendation-pipeline, base d9e31822e2a031b41a303f05ad1e96d29fa09d8f; 신규 producer full SHA 없음; ZIP은 미커밋 파일 사본 | D01–D03 양측 합의 및 게시할 변경 범위 검토 미완료; 신규 commit/push 미실행 | W4 담당자 / 양측 합의 내용을 반영·검증한 관련 변경만 commit/push하고 접근 가능한 40자 full SHA 교환 |
| actual producer image | PENDING / NOT_BUILT | docs/w4-question-core-producer.md에 host ports·안전 설정 이름·영속 저장 전제 기록; 실제 image digest 없음 | 실제 인증 context/policy adapter, 채택본 source pin, 배포 대상·volume·identity 미확정 | W4 배포 담당 (실명 PENDING) / source pin·adapter·volume 준비 후 immutable image 생성·배포 검증 |
| joint CT-12 | NOT_RUN | docs/w4-question-core-ct12-runbook-draft.md의 10개 시나리오와 증거 양식은 준비표; 로컬 검사를 공동 CT-12로 계산하지 않음 | 양측 합의·공유 commit·실제 context/producer/queue/identity·W1/W2 환경·공동 실행 담당 미확정 | W4 실행 책임, W1/W2 경계 담당과 일정·teardown 책임의 상호 확인 PENDING / 격리 환경·runbook 합의 후 실행 |

안전한 설정 변수명만: W4_CORE_OUTBOX_PATH, W4_CORE_SCHEMA_PATH, W4_CORE_SCHEMA_SHA256, W4_CORE_W1_FULL_SHA, W4_CORE_MAIN_QUEUE_URL, W4_CORE_MAIN_QUEUE_ARN, AWS_REGION, W4_CORE_SEND_ENABLED
실제 secret/token/운영 DB DSN/queue URL/role ARN: 포함하지 않음

## F. 채택 후 W4가 추가로 제공할 artifact

- W4 producer/outbox/relay를 포함한 접근 가능한 full commit SHA: PENDING — W4 담당자가 D01–D03 합의와 변경 범위 검토 후 관련 코드·schema·fixture를 검증·commit/push하고 제공. 현재 base SHA와 ZIP은 대체 근거가 아님
- 합의 schema와 valid/negative fixture 및 canonical digest vector 경로: PENDING — 현재 검토 후보는 samples/question-core-candidate-20260919/upstream/w4-question-core-decision.event.schema.json, core-required.json, non-core-optional.json, negative-events.json, policy-boundary.json, digest-vectors.json. 정식 version·16KiB 로컬 상한·canonical digest 규칙 합의 후 adopted 경로와 양측 commit pin 제공
- candidate와 adopted schema 차이 및 migration/compatibility 설명: PENDING — 현재 adopted schema가 없어 실제 diff 없음. 확정 후 version/필드/type/제약 차이·호환성·fixture/digest 영향·미전송 outbox 처리 방안을 문서화. 기존 저장 body/ID의 임의 변환 또는 후보 status 이름만 바꾸는 활성화 금지
- actual producer immutable image digest: PENDING — 실제 인증 context/policy adapter, 채택본 full SHA 및 배포 대상·volume·identity를 준비한 뒤 W4 배포 담당이 image 생성·검증 후 제공
- W4 workload send role ARN 및 SQS SenderId stable role ID: PENDING — D01~D03 합의와 격리 queue 준비 후에만 안전 채널로 제공. 발급 owner·실제 값 미확정
- CT-12 실행 담당, 가능한 조건, teardown 책임: W4 producer/outbox/relay 실행·자체 테스트 프로세스/로컬 DB 정리 책임은 W4. W1 consumer/queue/DB·공용 AWS 자원 및 W2 command 경계의 실행·teardown 담당과 일정은 PENDING (W1/W2 담당과 합의 필요). 양측 commit·실제 adapter/image·격리 queue/identity·runbook 준비 후 실행; 공동 정리 완료 증거도 기록
```

양식의 승인 owner는 실제 지정 자료가 없어 `PENDING`으로 남겼다. 담당 실명·일정·ARN·SenderId·queue URL은 추정하지 않았다.
설정 이름은 host에서 객체에 주입할 이름이며 환경변수만으로 시작되는 배포 CLI가 구현됐다는 뜻이 아니다.

[후보 출처·원문 hash](../samples/question-core-candidate-20260919/source-provenance.json) · [관련73개 및 복구 결과](../output/question-core-candidate-20260919/local/summary.json) · [전체454개 결과](../output/question-core-candidate-20260919/full/summary.json) · [전달 안내](w4-question-core-mandatory-r3-handoff-2026-09-19.md).
73개·454개는 직전 r3에서 실제 실행한 로컬 결과이며 이번 형식 보완에서 재실행하지 않았다. 검증 당시 source 219개를 관련/전체 검사 manifest 각각과 다시 hash 대조했고 모두 일치했다.
실제 SQS·W1 인증 context·IAM·PostgreSQL·공동 CT-12·LLM·원격 CI를 이번에 실행하지 않았다.
