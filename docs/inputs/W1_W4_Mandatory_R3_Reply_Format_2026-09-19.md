# W1 → W4 필수 r3 회신 형식 — 후보 계약 채택 전 최종 확인

작성일: 2026-09-19  
송신: W1  
수신: W4  
상태: **W4 r2 보완 요청 / 이 문서의 모든 필수 칸이 채워지기 전 W1 채택·AWS 연결·공동 CT-12 시작 불가**

## 1. 왜 r2만으로는 충분하지 않은가

W4 r2 전달본은 로컬 producer/outbox/relay 및 59개 로컬 검사를 제공한 점은 확인했다.
그러나 r2의 자체 상태는 아래와 같다.

| W4 r2 근거 | 기록된 상태 | W1 판정 |
| --- | --- | --- |
| `SOURCE-STATE.json` | `candidate_originals_received: 0` | 후보 원문을 실제 검토하지 않았으므로 D01 확정 회신이 아님 |
| `samples/question-core-review-20260919/source-review.json` | 두 후보 모두 `ORIGINAL_NOT_RECEIVED` | review SHA만 본 상태이며 원문 byte 검증이 없음 |
| `docs/w4-required-contracts-reply-2026-09-19-r2.md` D01 | version·제약 보류 | 후보 schema의 실제 필드·const·required·allOf를 최종 수락하지 않음 |
| 같은 문서 D02 | P2/P3 운영 승인 보류 | 정책 승인 owner·해제 조건이 아직 확정되지 않음 |
| 같은 문서 D08 | producer/outbox accessible full SHA `PENDING` | W4 로컬 구현은 재현 가능한 공유 artifact가 아님 |
| 같은 문서 D09 | `NOT_RUN` | 실제 queue/IAM/PostgreSQL/W1 consumer/W2 경계 공동 CT-12 미실행 |

따라서 W4 r2는 유효한 **pre-adoption 준비 회신**이지만, W1–W4 계약 채택 또는 runtime
시작 근거는 아니다.

## 2. W4가 검토해야 하는 유일한 후보 원문

W4는 다음 문서를 입력으로 사용한다. 이 문서는 두 후보 원문 전문을 포함하므로 W4 저장소에
`specs/**`가 없거나 Git commit SHA가 없어도 검토할 수 있다.

- 입력 문서: `md/w4/W1_W4_Candidate_Contract_Source_2026-09-19.md`
- 후보 A (`w4-adoption.md`) SHA-256:
  `6b4bfe3b0796c376b9b5f2831e66aaf526c3f27f94e80f5112f2df0d559b537f`
- 후보 B (`w4-question-core-decision.event.schema.json`) SHA-256:
  `1eb0506d9b13e22198ea11fb5fccd628096de2903b0fe5b1da3d383928d8407a`

위 SHA-256은 원문 동일성 확인용이다. 현재 W1 `develop` SHA
`bb27a692cf002100a3f773df7e434e90fe03f83f` 또는 후보 SHA-256을 W1–W4 **채택 완료
contract commit SHA**로 기록하면 안 된다.

## 3. W4 r3 회신의 작성 규칙

1. 아래 §4 양식을 그대로 복사하여 모든 칸을 채운다.
2. 각 D01 항목은 `채택`, `수정`, `보류` 중 하나를 반드시 선택한다. “전체 동의”나
   “기존 회신 참조”는 허용하지 않는다.
3. `수정`이면 field path, 기존/제안 type·값·의미, 호환성, fixture/digest 영향을 반드시 쓴다.
4. `보류`이면 W4 책임 owner, 외부 승인 owner, blocker, 해제 조건을 쓴다.
5. 정책 미승인과 W4 구현 미커밋은 숨기지 않고 `PENDING`으로 기록한다. 임의 milestone,
   IAM principal, queue URL, secret, 운영 DSN을 만들지 않는다.
6. r3는 W4 입장과 증거를 기록하는 문서다. W1·W2·W3의 동의를 대신 선언하지 않는다.

## 4. 복사해 작성할 W4 r3 필수 회신 양식

아래 코드 블록 전체를 W4 r3에 포함한다. `<...>`를 실제 값 또는 명시적 `PENDING`으로
치환한다.

```text
# W4 → W1 Question Core pre-adoption r3 회신

상태: <PRE_ADOPTION_REPLY_COMPLETE 또는 PENDING 항목을 포함한 상태>
W4 review artifact version: <version>
W4 repository/access path: <repository 또는 안전한 접근 경로>
W4 current local base SHA: <40-char SHA 또는 PENDING>
W4 producer/outbox accessible full SHA: <40-char SHA 또는 PENDING>

## A. 후보 원문 byte 수령 및 대조

candidate_originals_received: <2>

| 후보 | 수령한 문서/section | 계산한 SHA-256 | W1 제공 SHA-256 | byte_verified |
| --- | --- | --- | --- | --- |
| w4-adoption.md | <document path + section> | <sha256> | 6b4bfe3b0796c376b9b5f2831e66aaf526c3f27f94e80f5112f2df0d559b537f | <true/false> |
| w4-question-core-decision.event.schema.json | <document path + section> | <sha256> | 1eb0506d9b13e22198ea11fb5fccd628096de2903b0fe5b1da3d383928d8407a | <true/false> |

원문 byte가 일치하지 않으면: <불일치 대상, 계산 hash, 중단 이유. 일치하면 NONE>

## B. D01 wire 계약 — 후보 원문 기준의 최종 항목별 판정

| ID | 후보 요구 | 상태 (채택/수정/보류) | W4 근거·코드/테스트 경로 | 수정안 또는 blocker |
| --- | --- | --- | --- | --- |
| D01-01 | flat event 및 `schema_version=w4.private.question-core-decision/0.1-candidate`, `message_type=w4.private.w1.question-core-decision`, `visibility_scope=PRIVATE` |  |  |  |
| D01-02 | W1-issued `job_id` 필수, Job 추정 및 public/client/LLM 주입 금지 |  |  |  |
| D01-03 | `message_id`와 `decision_id` 분리, retry에서 ID·`occurred_at`·canonical body·digest 불변 |  |  |  |
| D01-04 | `decision_scope=QUESTION_MATCHING`, `decision_owner=W4`, `producer=w4` 고정 |  |  |  |
| D01-05 | `company_id=null`, `question_version_id`·`source_id`·`analysis_input_version`·positive `decision_version` 포함 |  |  |  |
| D01-06 | owner/project/company hint 및 추가 field 제외, `additionalProperties=false` |  |  |  |
| D01-07 | `decision_code`와 `is_core`의 Core/Non-Core 일치, `reason_code` 형식·비민감 규칙 |  |  |  |
| D01-08 | W4 전용 main queue, send-only principal. body `producer`는 인증 근거가 아님 |  |  |  |

D01 수정 diff/fixture 영향: <없으면 NONE>
D01 보류 항목별 owner·해제 조건: <없으면 NONE>

## C. D02 P1–P3 정책

| ID | 정책 | W4 상태 (채택/수정/보류) | 정책 승인 owner | blocker | 운영 enablement 조건 |
| --- | --- | --- | --- | --- |
| P1 | 승인된 문항/Source 근거만 판단하며 LLM SUPPORTED·경험 순위·W3 C01 USABLE을 자동 Core로 바꾸지 않음 |  |  |  |  |
| P2 | 필수 자료=CORE_REQUIRED, 보완=NON_CORE_OPTIONAL, 불명확=발행 보류 |  |  |  |  |
| P3 | Core reason=QUESTION_EVIDENCE_REQUIRED, Non-Core reason=SUPPLEMENTARY_CONTEXT, reason에 원문/개인정보 금지 |  |  |  |  |

현재 REAL 사용자 자료 발행 상태: <DISABLED. 다른 값이면 승인 근거와 W1/W4 합의 기록 필수>

## D. D03 T1–T5 책임 경계

| ID | 책임 | W4 상태 (채택/수정/보류) | 이견 / 상대 팀 확인 필요 사항 |
| --- | --- | --- | --- |
| T1 W4 | trusted `job_id` 보존, 의미 판단, immutable body/ID, durable outbox, send 직전 currentness 검사, send-only relay |  |  |
| T2 W1 | sender 인증, Job/owner/project/question/Source/input/epoch/fence 검사, receipt/decision/binding 원자 저장, user retry, W2 command/lookup |  |  |
| T3 W2 | W1 승인 command/protected lookup만 소비. W4 receipt는 실행 완료가 아님 |  |  |
| T4 W3 | W3 usability와 W4 inbound/W2 ACK는 상호 대체하지 않음 |  |  |
| T5 retry | W4 receipt는 재개 신호가 아니며 명시적 user retry만 새 fence/W2 command를 생성 |  |  |

## E. W4 구현·인계 상태

| 영역 | 현재 상태 | 근거 경로/명령·결과 | 아직 미완료인 이유 | W4 담당 / 준비 완료 조건 |
| --- | --- | --- | --- | --- |
| candidate schema/fixture 적용 |  |  |  |  |
| producer codec |  |  |  |  |
| durable outbox/restart |  |  |  |  |
| currentness relay |  |  |  |  |
| send-only SQS adapter |  |  |  |  |
| accessible commit/push |  |  |  |  |
| actual producer image |  |  |  |  |
| joint CT-12 |  |  |  |  |

안전한 설정 변수명만: <comma-separated names 또는 PENDING>
실제 secret/token/운영 DB DSN/queue URL/role ARN: 포함하지 않음

## F. 채택 후 W4가 추가로 제공할 artifact

- W4 producer/outbox/relay를 포함한 접근 가능한 full commit SHA: <조건 또는 PENDING>
- 합의 schema와 valid/negative fixture 및 canonical digest vector 경로: <조건 또는 PENDING>
- candidate와 adopted schema 차이 및 migration/compatibility 설명: <조건 또는 PENDING>
- actual producer immutable image digest: <조건 또는 PENDING>
- W4 workload send role ARN 및 SQS SenderId stable role ID: <D01~D03 합의와 격리 queue 준비 후에만 안전 채널로 제공>
- CT-12 실행 담당, 가능한 조건, teardown 책임: <조건 또는 PENDING>
```

## 5. W1의 수락 기준과 다음 단계

W1은 r3가 아래를 모두 만족할 때만 **계약 채택 구현 입력이 준비됨**으로 바꾼다.

1. 후보 원문 두 개의 `byte_verified=true`와 제공 hash 일치
2. D01-01~08에 빠짐없는 항목별 판정과 수정/보류 근거
3. P1–P3별 정책 owner·blocker·enablement 조건
4. T1–T5별 책임 판정과 이견 owner
5. W4 local-only 범위, full SHA 부재, actual queue/CT-12 미실행 여부를 명확히 분리

이 수락은 W4 producer의 운영 준비, W4 실제 role 생성, AWS 권한 부여, W1 consumer 기동,
공동 CT-12 완료를 뜻하지 않는다. 그 단계는 합의된 schema/fixture/codec을 양측이 commit·push한
뒤에 시작한다.

## 6. 이 회신에서 요구하지 않는 것

W4는 이 r3 회신을 위해 다음을 제공하거나 생성할 필요가 없다.

- W1 PostgreSQL 접근·migration·RLS 구현
- W1 queue receive/delete/ChangeVisibility/Purge 권한
- W2 commit-gate 구현 또는 W3 usability 계약 변경
- 실제 secret, token, 운영 DB DSN, raw user data
- 합의 전 추정한 AWS role ARN, SenderId, queue URL

W4가 지금 보내야 할 것은 **후보를 실제로 검토한 항목별 계약 회신과 미완료 상태의 정확한
기록**이다.

## 7. 근거

- `md/w4/W1_W4_Candidate_Contract_Source_2026-09-19.md`: 후보 원문 전문과 SHA-256
- `md/W1_W4_Required_Contracts_2026-09-19.md`: D01–D10, 책임 경계, W4 필수 산출물
- `w4/EPICK_W4_PreAdoption_Review_2026-09-19_r2/SOURCE-STATE.json`: r2 candidate 원문 0건,
  local-only 상태
- `w4/EPICK_W4_PreAdoption_Review_2026-09-19_r2/docs/w4-required-contracts-reply-2026-09-19-r2.md`:
  r2 D01 보류, P2/P3 승인 보류, local producer/full SHA/CT-12 상태
