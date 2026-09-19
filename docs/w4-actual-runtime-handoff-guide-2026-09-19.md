> 2026-09-20 후속: [HTTP runtime r5](w4-http-runtime-handoff-2026-09-20.md)가 실행 환경·context 계약 미정 상태를 대체합니다. 아래는 r4 당시 기록입니다.

# W4 실제 runtime 준비 검토 전달 안내 · 2026-09-19 r4

전달 파일: **EPICK_W4_Runtime_Readiness_2026-09-19_r4.zip**.
[실제 runtime A–F 회신](w4-actual-runtime-handoff-reply-2026-09-19.md)을 먼저 읽는다.
이 ZIP은 실제 runtime 준비 요청에 대한 수정 코드·로컬 검증·미완료 조건 자료다. 접근 가능한 commit, 실제 image, IAM identity 또는 SQS 실행 증거를 대신하지 않는다. 외부 발송하지 않았다.

## 달라진 내용

W1이 r3/r3.1의 후보 검토를 수령한 뒤 실제 runtime 선행물을 요청했다.
W1 commit `519b9127227ad3ca6483a61a5143d355c5eea5eb`의 adopted schema도 wire version은 `0.1-candidate`다.
W4의 기존 문자열 차단과 충돌하는 것을 재현했고, 확인된 commit/schema hash 쌍에만 wire 채택 예외를 추가했다.
원래 후보·잘못된 pin·미승인 상태는 계속 차단되며 default send=false·REAL/policy 제한을 유지한다.
기존 candidate outbox의 ID/body/hash를 수정해 전송하지 않는다. 새 schema와 맞지 않으면 BLOCKED 처리한다.

## 파일별 역할

| 파일 | 기능 |
| --- | --- |
| [runtime 회신](w4-actual-runtime-handoff-reply-2026-09-19.md) | 필수 A–F와 각 PENDING의 owner·해제 조건, queue 준비 순서 조정 요청 |
| [W1 요청 원본](inputs/W1_W4_Actual_Runtime_Handoff_Request_2026-09-19.md) | 실제 runtime 선행물과 종료 기준 |
| [원본 출처](../samples/question-core-w1-runtime-20260919/source-provenance.json) | W1 commit·원본7개 파일 byte hash |
| [W1 계약 README](../samples/question-core-w1-runtime-20260919/W1-CONTRACT-README.md) | W1 wire 채택과 runtime/정책 승인의 구분 |
| [adopted schema](../samples/question-core-w1-runtime-20260919/question-core-decision.event.schema.json) | W1에서 실제 사용하는 wire 검증 원본. 후보와 검증 의미 동일 |
| [정상 Core](../samples/question-core-w1-runtime-20260919/valid-core.json), [Non-Core](../samples/question-core-w1-runtime-20260919/valid-non-core.json), [negative](../samples/question-core-w1-runtime-20260919/negative-events.json), [digest](../samples/question-core-w1-runtime-20260919/digest-vectors.json) | W1 commit에 있는 원본 fixture/vector |
| [codec](../epick_w4/question_core_contract.py) | 이번 runtime 코드 변경. 정확한 W1 commit+schema hash만 candidate 버전 예외로 인정 |
| [producer](../epick_w4/question_core_producer.py), [outbox](../epick_w4/question_core_outbox.py), [relay](../epick_w4/question_core_relay.py) | 기존 trusted port·영속 저장·매 송신 재검사·send-only 코드, 이번 변경 없음 |
| [로컬 예제](../examples/w4_question_core_local.py) | w1-adopted 모드를 추가한 합성 context/policy·Fake Queue 복구 실행. 실제 adapter 아님 |
| [새 테스트](../tests/test_question_core_w1_adopted.py) | 원본/fixture/digest 호환·pin 오류·송신 제한·이전 outbox 차단·복구 12개 |
| [관련 검증 실행](../scripts/verify-question-core-producer.py) | w1-adopted 모드로 관련 테스트85개와 로컬 프로세스 복구 결과 기록 |
| [관련 최종 결과](../output/question-core-runtime-readiness-20260919/local-final/summary.json), [전체 최종 결과](../output/question-core-runtime-readiness-20260919/full-final/summary.json) | 관련85·전체466 통과. 두 수치는 중복을 포함하며 합산하지 않음 |
| [준비 상태 검증](../output/question-core-runtime-readiness-20260919/readiness-verification.json) | 재현한 문제·수정 후 경계·source hash 대조·실제 runtime 미완료 상태 |
| ZIP 루트 SOURCE-STATE.json / MANIFEST.json | 현재 상태와 파일별 hash. 이전 r2/r3/r3.1 자료는 당시 기록 |

## 재현

```powershell
uv sync --locked --extra api --extra test
uv run --locked --extra api --extra test python scripts/verify-question-core-producer.py --contract w1-adopted --output-dir output/runtime-local-new
uv run --locked --extra api --extra test python scripts/verify_service_handoff.py --output-dir output/runtime-full-new
```

출력 경로는 존재하지 않는 새 디렉터리를 사용한다. 실제 AWS·모델·팀 API에 연결하지 않는다.
코드의 SQS 검사는 Stubber이고 복구는 로컬 SQLite/Fake Queue다. 실제 송신·image·공동 CT-12는 NOT_RUN이다.
이번 전체466개에는 신규12개가 포함되고 실패·오류·skip0이다. 가상 HTTP2개도 통과했다.

## W1에 전달할 문안

> r3/r3.1 수령 확인 및 실제 runtime 요청을 확인했습니다. A–F 회신과 W1 commit 519b9127 기준 wire 호환 수정·로컬 검증 자료를 첨부합니다.
> W1 adopted schema가 candidate version을 유지하므로, 정확한 commit/schema hash로 확인한 경우에만 허용하도록 W4 codec을 수정했습니다. 관련85개·전체466개 및 로컬 복구가 통과했습니다.
> 실제 context/currentness adapter 구현에는 서비스 간 인증·필드/epoch/fence·갱신/오류 계약이 필요합니다. 기존 Job 조회만으로 대체하지 않겠습니다.
> §4의 queue 생성이 A–F 완료 뒤라 E의 실제 시험과 선후관계가 순환합니다. 선행 artifact/identity와 정책 제한 확인 → 격리 queue 준비 → 실제 E 증거 → 공동 CT-12 순서로 조정하거나 기존 시험 queue를 지정해 주세요.
> 배포·IAM 담당과 정책 owner/revision도 확인이 필요합니다. 실제 image/SQS·공동 CT-12는 미실행이고 REAL은 DISABLED입니다.

위는 미발송 초안이다. 실제 Role/SenderId/queue/secret은 이 문서나 채팅에 적지 않고 승인된 안전 채널에서 취급한다.
