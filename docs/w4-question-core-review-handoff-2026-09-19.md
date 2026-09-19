# W4 계약 검토 전달 안내 · 2026-09-19 r2

> 이전 기록이다. 후보 원문 수령·검증 후 [r3 회신](w4-required-contracts-reply-2026-09-19-r3.md)으로 갱신했다. 아래 원문 미수령 상태는 당시 기록이다.

상태: **후보 계약 합의 전 검토 자료 / 외부 발송 전**.
먼저 [항목별 회신 r2](w4-required-contracts-reply-2026-09-19-r2.md)를 읽는다.
이번 자료는 직전 구현에 9월 19일 추가 요청의 합의 순서·기준 검증·준비표를 반영한 것이다.

## 이번에 처리한 내용

- W1 요청서의 추가 §0 확인. 후보 검토·D01–D03 합의를 먼저 하고 채택 완료 SHA는 이후 교환하도록 정정.
- W1 기존 기준 bb27a692cf002100a3f773df7e434e90fe03f83f의 원본 3개 체크섬 대조와 계약 경계 11개 확인.
- D01 8개 항목, P1–P3 정책, T1–T5 책임에 대한 W4 입장과 남은 승인 조건 정리.
- D04–D10 구현·검증·인계 조건과 공동 CT-12 10개 시나리오 준비.
- 기존 producer/outbox/relay를 전달 자료에 포함. 후보 원문이 없어 해당 형식에 맞춘 runtime 변경은 아직 하지 않음.

## 파일별 기능

| 파일 | 기능 |
| --- | --- |
| [회신 r2](w4-required-contracts-reply-2026-09-19-r2.md) | W1에 전달할 항목별 수용·보류·담당·해제 조건 |
| [코드 실행 안내](w4-question-core-producer.md) | host 연결, SQLite 운영 조건, send-only 설정, 재현 명령 |
| [CT-12 준비표](w4-question-core-ct12-runbook-draft.md) | 공동 검증 전 환경·역할·10개 시나리오·증거 양식 |
| [W1 추가 요청 원문](inputs/W1_W4_Required_Contracts_2026-09-19.md) | 후보 문서 경로·review SHA·D01–D10의 근거. 후보 2개 본문은 포함되지 않음 |
| [기준 검증 기록](../samples/question-core-review-20260919/source-review.json) | 원본 3개 SHA, 후보 경로의 기준 커밋 내 부재, 경계 11개 결과 |
| [codec](../epick_w4/question_core_contract.py) | 외부 schema checksum·flat event·canonical digest 검사, 미채택 전송 차단 |
| [producer](../epick_w4/question_core_producer.py) | host context·명시적 policy로 Job에 결속된 메시지 준비, REAL 차단 |
| [outbox](../epick_w4/question_core_outbox.py) | 결정·본문의 영속 원자 저장, 중복·충돌·lease·재시작 |
| [relay](../epick_w4/question_core_relay.py) | 매 전송 currentness 검사, 불변 재전송, SQS send-only adapter |
| [로컬 시연](../examples/w4_question_core_local.py) | 합성 context/policy, 모의 queue, 실제 프로세스 종료·복구 |
| [producer 테스트](../tests/test_question_core_producer.py) / [SQS 테스트](../tests/test_question_core_sqs.py) | SQLite/currentness/재시도와 Stubber SDK 검사 |
| [기준 검증 스크립트](../scripts/verify-question-core-review.py) | 고정 W1 Git 원본·checksum·기존 계약 경계를 재현 |
| [로컬 검증 스크립트](../scripts/verify-question-core-producer.py) | producer 테스트와 별도 프로세스 복구 증거 생성 |
| [압축 스크립트](../scripts/package-question-core-review.py) | 검증 당시 소스 일치, 현재 문서 링크, ZIP CRC·모든 파일 checksum 검사 |

압축에는 위 핵심 파일 외에 import 의존성을 충족하는 epick_w4 전체 코드, 샘플·스키마·테스트·잠금 파일과 참고 문서가 있다.
00-START-HERE.md가 입구이며 SOURCE-STATE.json은 미완료 상태, MANIFEST.json은 파일 SHA-256을 기록한다.
모델 가중치·자격증명·가상환경·Git metadata·실행 DB는 포함하지 않는다.
과거 문서의 완료 수치·경로는 당시 기록이며 최신 상태는 r2 회신을 따른다.

## 검증 근거의 구분

- [이번 기준 검증](../output/question-core-review-20260919/baseline/source-review.json): 원본 3개·경계 조건 11개.
- [이번 producer 재검증](../output/question-core-review-20260919/local/summary.json): **59개 통과, 실패·오류·skip 0**. 실제 프로세스 종료·복구 시연도 통과했고 동일 body 재전송과 임시 DB 정리를 확인했다. queue는 모의 구현이다.
- [직전 전체 440개 결과](../output/question-core-producer-20260919/full/summary.json): 이전 실행 기록. 이번 회신 개정에서 전체 suite를 재실행한 것으로 표시하지 않는다.
- 실제 SQS/IAM/PostgreSQL 공동 검증·LLM 추론·GitHub CI는 이번에 실행하지 않았다.

후보 2개 원문은 아직 없다. 포함된 기존 W1 schema를 후보 flat 규격으로 쓰면 안 된다.
계약 채택·운영 승인·접근 가능한 새 full SHA·공동 CT-12가 끝났다고 제출하지 않는다.

## W1에 전달할 짧은 문안

> 추가된 §0의 합의 순서를 수용합니다. 채택 완료 SHA를 선행 조건으로 요구하지 않고 후보 검토 → D01–D03 합의 → 채택본 commit/SHA 교환 순으로 진행하겠습니다.
>
> W4 항목별 회신과 producer/outbox/relay 로컬 구현·검증 자료를 준비했습니다. 기존 기준 bb27a692…의 원본 3개 checksum과 계약 경계 11개도 확인했습니다. 실제 전송·공동 CT-12 완료 자료는 아닙니다.
>
> 요청서에는 후보 2개의 경로와 review SHA만 있어, w4-adoption.md와 w4-question-core-decision.event.schema.json의 원문 파일 또는 읽을 수 있는 경로를 부탁드립니다. 미커밋 검토본이어도 됩니다. D01–D03 회신과 P1–P3 정책 승인자·활성화 조건도 확인 부탁드립니다.

위 문안은 미발송 초안이다. 키·비밀번호·운영 DSN이나 실제 사용자 원문을 포함하지 않는다.
