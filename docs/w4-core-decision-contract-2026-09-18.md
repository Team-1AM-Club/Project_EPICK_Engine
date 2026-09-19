# W4 → W1 Core Decision 계약 초안

작성일: 2026-09-18. 상태: **W4_UNADOPTED_PROPOSAL_TRANSPORT_DISCONNECTED**.

W4가 특정 문항을 판단하는 데 Source가 필수인지 W1에 알리는 메시지를 준비한다. 경험 추천 순위, W3 C01 지식 전달, W2 수집 결과·commit-gate ACK와 다른 계약이다. 이번 구현은 가상 입력의 메시지 생성·검사·재시도 전 재검사까지다. 실제 전송, 자동 필수성 판단, W1 소비·저장은 구현하지 않았다.

## 기준과 산출물

- W1 기준: [Project_EPICK_Service afec08a9602132e5e433b523b0b6804850440524](https://github.com/Team-1AM-Club/Project_EPICK_Service/tree/afec08a9602132e5e433b523b0b6804850440524).
- [provenance와 파일별 SHA-256](../epick_w4/core_decision_schemas/baseline.json)에 지정한 8개 파일을 해당 Git object에서 원본 바이트 그대로 복사했다. 작업 트리의 수정본을 기준으로 삼지 않는다.
- [생성·검사 코드](../epick_w4/core_decision.py), [오프라인 시연](../examples/w4_core_decision_demo.py), [테스트](../tests/test_core_decision.py).
- [필수 Source 정상 메시지](../samples/core-decision/core-required.json), [보조 Source 정상 메시지](../samples/core-decision/non-core.json), [거부 메시지 20개](../samples/core-decision/negative-messages.json), [수신 확인 6종](../samples/core-decision/receipts.json).
- [서버 문맥 제안](../samples/core-decision/context.json)과 [그 스키마](../samples/core-decision/context.schema.json)는 W4 로컬 초안이다. W1 wire schema에 필드를 추가한 것이 아니다.

W1 기준 SHA는 접근 가능한 기존 계약 pin이다. **새 W4 구현은 로컬 미커밋 산출물**이며 W4 완료 full SHA나 팀 채택 정본은 아직 없다. ZIP과 manifest는 파일 전달·대조용이고 Git pin을 대신하지 않는다.

## 전송할 객체

[Envelope](../epick_w4/core_decision_schemas/envelope.schema.json)와 [payload](../epick_w4/core_decision_schemas/payload.schema.json)를 모두 검증하고 W4 범위를 추가로 검사한다.

| 필드 | W4 값·규칙 |
| --- | --- |
| envelope `schema_version` | `w1.private.v1` |
| `message_type` / payload `schema_version` | `w1.core-source-decision.v1` |
| `producer` / `visibility_scope` | `w4` / `PRIVATE` |
| `channel` | `w1.private.w4.core-source-decision.v1` |
| `message_id`, `decision_id` | 서버가 제공하는 UUID. 동일 제출의 재시도에서는 변경하지 않음 |
| `occurred_at` | 시간대가 있는 RFC 3339 시각. 재시도 시 보존 |
| `decision_scope` | `QUESTION_MATCHING` |
| `company_id` | `null` |
| `question_version_id`, `source_id` | 서버가 결속한 UUID |
| `analysis_input_version` | 1~64자 불투명 문자열. 숫자로 변환·정렬하지 않음 |
| `decision_version` | 1 이상의 정수. 새 결정은 현재 cursor보다 커야 함 |
| `decision_code` / `is_core` | `CORE_REQUIRED` / `true`, 또는 `NON_CORE_OPTIONAL` / `false` |
| `reason_code` | 대문자로 시작하는 1~64자 코드. 원문·자유 서술을 넣지 않음 |

추가 필드는 거부한다. Python bool을 정수 버전으로 받거나 `3.0`을 결정 버전으로 받지 않는다. JSON 객체는 64,000 UTF-8 bytes 이하로 제한하며 오류에는 입력 본문을 복사하지 않는다. 이 타입·크기 제한은 W4 생성기의 추가 방어 규칙이다.

`QUESTION_EVIDENCE_REQUIRED`는 **가상 시연용 제안 reason**이다. 이를 팀이 채택한 판단 정책이나 모든 문항에 적용할 규칙으로 해석하지 않는다. 함수에는 `decision_code`와 `reason_code`가 명시적으로 필요하다. LLM의 `SUPPORTED`, 추천 1순위, C01 `USABLE`을 필수 Source로 자동 변환하지 않는다. 반대로 아직 수집되지 않은 Source에 수집을 요청할 수 있으므로 C01 `USABLE`을 메시지 생성의 선행 조건으로 강제하지 않는다.

## 소유자와 현재성

`DecisionContext`는 **인증된 서버가 현재 저장소에서 조회·검증해 제공할 로컬 문맥 제안**이다. 브라우저 요청의 owner나 자기 선언 `SYNTHETIC`만으로 권한을 증명할 수 없다. 현재 코드는 지정된 소유자와 문맥의 일치만 검사하며 인증 서버·DB 조회기는 없다.

문맥에는 owner, project, question version, Source, 수집 대상 company, 불투명 입력 버전, 권한 revision, 현재 결정 cursor와 처리 허용·문항 현재성·Source 활성 플래그가 있다. 회사 UUID는 `collection_company_id`로 로컬 문맥에만 보관한다. 이는 W1 회사 결속 충돌을 우회하거나 회사 UUID를 실제로 확정하는 기능이 아니다.

- `prepare_decision(...)`: 명시적인 정책 결정을 pinned W1 메시지로 만들고 문맥·메시지 해시를 기록한다. `REAL`은 거부한다.
- `check_current(...)`: 호출자가 다시 조회한 문맥과 준비 객체를 비교한다. 소유자/권한/문항/Source/회사/입력 버전 변경, 비활성 Source, 권한 철회, 과거로 돌아간 cursor, 더 최신 결정은 차단한다. 반환값은 전송 가능한 형태의 객체일 뿐 전송은 하지 않는다.
- `receipt_outcome(...)`: W1 receipt의 schema, consumer, message ID를 검증한다. 이 함수는 권한 조회나 결과 공개 작업을 수행하지 않는다.

해시는 로컬 저장 객체의 일관성을 검사하는 수단이며 서명·인증 수단이 아니다. 호스트는 문맥과 준비 객체를 신뢰 경계 안에 저장해야 한다. 실제 연결 시 W1이 인증 principal과 owner/project/question/Source 연결을 다시 검사하고, 현재성·삭제·동시성 검사를 DB 트랜잭션 안에서 수행해야 한다. 이 동작은 이번 로컬 검사로 입증하지 않았다.

## 버전·중복·재시도

W1 README에 따르면 동일 consumer/message ID는 `DUPLICATE`, 동일 scope/대상/Source/analysis input에서 이미 적용됐거나 낮은 decision version은 `STALE_DISCARDED`다. W4는 같은 제출의 ID·시각·본문을 고정한다. 현재 W4 모듈에 영속 outbox나 중복 처리 DB는 없다.

1. 호스트가 해당 키의 현재 version을 읽고 명시적으로 새 version을 배정한다. 코드가 전역 카운터를 추정하거나 버전을 자동 증가시키지 않는다.
2. 전송 직전과 재시도 직전에 현재 문맥을 다시 읽어 `check_current`를 실행해야 한다.
3. ACK 유실 후 현재 cursor가 준비 메시지 version과 같아도 같은 메시지 재시도 준비는 허용한다. 이는 W1 적용 성공의 추정이 아니다. W1이 `DUPLICATE` 또는 `STALE_DISCARDED` 등을 실제 상태로 판정해야 한다.
4. 더 높은 version이 관측되거나 입력/권한이 바뀌면 오래된 메시지는 보낼 수 없다. 같은 ID의 본문 수정도 일관성 검사로 차단한다. 여러 프로세스 간 경쟁·재시작 내구성은 아직 미구현이다.

W1 원본 `analysis_input_version="question-input:v4"`와 `decision_version=3`은 서로 다른 값이다. W1이 W2 명령을 만들 때 **`input_version`, `core_source_decision.decision_revision`, `core_source_decision.analysis_input_version`은 모두 숫자 `3`**으로 결속한다. 원본 입력 문자열은 W1 Core pin/Job에 남긴다. lower-case wire producer `w4`와 W2 명령 내부 decision owner `W4`도 구분한다.

## W1 receipt와 W2 ACK 구분

| W1 outcome | 초안의 처리 |
| --- | --- |
| APPLIED | 수신 적용 결과로 기록. 수집 완료·현재 결과 공개로 승격하지 않음 |
| DUPLICATE | 중복 수신 결과. 새 성공 전이나 현재 공개를 보장하지 않음 |
| STALE_DISCARDED | 같은 오래된 메시지를 계속 재시도하지 않음. 현재 문맥 재조회 필요 |
| REJECTED_SCHEMA / REJECTED_PRINCIPAL | 동일 내용 자동 재전송 대상으로 분류하지 않음. 계약·권한 수정 필요 |
| RETRYABLE_INFRA_FAILURE | 현재 문맥 재검사 후 동일 메시지 재시도 대상으로 분류 |

네트워크 오류로 receipt 자체가 없는 경우도 저장한 동일 메시지만 재시도해야 한다. 실제 전송·재시도 스케줄러는 없다. W2 제안의 APPLIED/DUPLICATE/REJECTED gate ACK는 여기의 receipt가 아니며 다른 schema의 메시지는 거부한다.

## 회사 결속 충돌의 직접 재현

[고정한 W1 검사 함수](../samples/core-decision/upstream/core_decision_binding.py)와 [W2 command schema](../samples/core-decision/upstream/w2-command.schema.json)를 변경하지 않고 실행했다. COMPANY_KNOWLEDGE 정상 대조군은 양쪽을 통과한다.

| QUESTION_MATCHING pin의 company | W2 command company | W2 schema | W1 binding |
| --- | --- | --- | --- |
| null | UUID | 통과 | 거부 |
| null | null | 거부 | 통과 |
| UUID | 같은 UUID | 통과 | 거부 |

W1은 QUESTION_MATCHING pin에 `company_id=null`을 요구하면서 command와 pin의 company가 같아야 한다고 검사한다. W2 schema는 company UUID를 요구한다. 지정 pin에서는 세 조건을 함께 만족할 수 없다. 로컬 데모의 `PASSED`는 이 충돌을 정확히 재현했다는 뜻이며 연결 성공이 아니다.

**수정 제안:** question-scoped Core 입력의 `company_id=null`은 유지하고 수집 대상 company를 별도의 인증된 owner/project/question/Source 연결에서 해석·검증한다. COMPANY_KNOWLEDGE의 동일 company 검사는 유지한다. W1 worker·relay·protected lookup 모두 회사 연결을 확인할 수 있는 계약이 필요하다. 구체적 관계 모델과 접근 권한은 W1이 확인해야 하며, 단순히 company 비교 한 줄을 제거하는 수정은 제안하지 않는다. 다른 해결안을 채택한다면 관련 schema·runtime·fixture를 함께 변경한 full SHA가 필요하다.

## 실행과 실제 검증 범위

프로젝트 루트에서 실행한다. 모델 서버·팀 API·자격증명은 필요 없다. output 경로는 기존 결과를 덮어쓰지 않도록 새 경로를 사용한다.

```powershell
uv sync --locked --extra api --extra test
uv run python -m unittest discover -s tests -p test_core_decision.py -v
uv run python scripts/demo-core-decision.py --output-dir output/core-decision-local-demo
uv run python scripts/verify_service_handoff.py --output-dir output/core-decision-local-verification
```

직접 실행: 기존 351개 + 신규 30개 = **381개 통과, 실패/오류/skip 0**. 가상 HTTP 시연 2개 통과(모의 호출 12회). Core Decision 정상 2개·거부 20개·receipt 6종·회사 충돌 3개 및 대조군 1개 검증. Ruff F 검사와 Git diff 공백 검사 통과. 실제 LLM 호출, 팀 W1/W2 queue, 실제 PostgreSQL, 공동 CT-12/CT15는 이번 작업에서 실행하지 않았다. W2 문서의 1006개·PostgreSQL 검증 수치를 우리의 실행 결과로 합산하지 않는다.

로컬 결과: [전체 검사](../output/core-decision-20260918/verification/summary.json), [Core 시연·충돌 재현](../output/core-decision-20260918/demo/core-decision-demo.json).

## 공동 CT-12로 넘어갈 조건

아래는 실행 제안이며 접근 가능한 W1 CT-12 정본을 확인한 완료 판정이 아니다.

- W1: 회사 충돌 수정 full SHA, canonical schema/fixture, 현재 문맥 조회·owner 결속 규칙, principal/channel 주입·격리 환경·정리 책임, receipt/재시도 경계와 CT-12 runbook 제공.
- W4/팀: Source 필수성 정책과 reason 목록 검토, W4 산출물의 접근 가능한 pin, 내구성 있는 메시지 저장·전송 adapter와 실패 재시도 구현. 현재 준비 상태는 codec/fixture만 완료다.
- 공동 실행: 정상 Core/non-Core, 다른 소유자, 문항·입력·권한 변경, 같은 메시지 재전달, ACK 유실 후 재시작, 낮은/동일/경쟁 version, 같은 ID의 다른 본문, company 불일치, 취소·삭제 후 늦은 메시지를 검증한다. 기대 receipt와 DB 전이는 W1 정본에 따라 확정해야 한다.
- Core 수신 적용과 W2 수집·commit gate·최종 공개는 따로 확인한다. 이 제안을 제출하는 것으로 W2 R3-01/03/04, T067 삭제 미구현, CT15가 해결되지는 않는다.
