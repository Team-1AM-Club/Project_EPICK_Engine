# W4 후보 원문 검토 전달 안내 · 2026-09-19 r3

상태: **후보 원문 확인·W4 codec 호환 수정·검토 회신 준비 / 양측 채택 전**.
[항목별 회신 r3](w4-required-contracts-reply-2026-09-19-r3.md)부터 읽는다.
이 문서는 직전 r3의 구현·검증 설명이다. **현재 전달본은 [필수 양식 회신 r3.1 안내](w4-question-core-mandatory-r3-handoff-2026-09-19.md)**다. r1/r2의 원문 미수령 상태는 역사적 기록이다.

## 이번 변경

- 전달서 §6·§7에서 후보 원문 두 개를 그대로 추출했고 두 SHA-256이 모두 일치했다.
- 기존 codec이 type:null을 읽지 못하는 오류를 재현·수정했다. 후보 schema 자체는 수정하지 않았다.
- 후보 version/type으로 메시지를 생성하는 합성 경로와 검증을 추가했다.
- reason 문자열의 schema 유효성과 운영 정책 승인을 분리했다.
- W1_CANDIDATE 상태와 후보 버전의 실제 전송 차단을 유지한다.
- 원문 A1 양식의 13개 행과 추가 회신 필드를 채웠다. 새 원문 사본이나 후보 commit을 다시 요청하지 않는다.

## 파일별 역할

| 파일 | 기능 |
| --- | --- |
| [회신 r3](w4-required-contracts-reply-2026-09-19-r3.md) | A1/P1–P3/T1–T5 수용·보류, 실제 구현 경계, SHA·운영 준비 조건 |
| [후보 원문 전달서](inputs/W1_W4_Candidate_Contract_Source_2026-09-19.md) | W1이 보낸 전문을 포함한 문서 원본 |
| [adoption 원문](../samples/question-core-candidate-20260919/upstream/w4-adoption.md) | 원문 A1 양식·정책·책임·Phase 2 기준 |
| [schema 원문](../samples/question-core-candidate-20260919/upstream/w4-question-core-decision.event.schema.json) | 변경하지 않은 후보 flat event 규격 |
| [출처·checksum](../samples/question-core-candidate-20260919/source-provenance.json) | 두 원문과 전달서·상태 이미지의 파일 동일성, 후보/기존 기준 SHA 구분 |
| [fixture manifest](../samples/question-core-candidate-20260919/manifest.json) | 정상2·거부/결속25·정책 경계·digest3개와 모든 파일 hash |
| [codec](../epick_w4/question_core_contract.py) | schema 검증, type:null 호환, canonical digest, 후보 전송 차단 |
| [producer](../epick_w4/question_core_producer.py) | trusted host Job context·명시적 policy로 준비, REAL 차단 |
| [outbox](../epick_w4/question_core_outbox.py) | SQLite 원자 저장·불변 ID/body·retry·lease·재시작 |
| [relay](../epick_w4/question_core_relay.py) | 발행 직전 현재성 검사, 동일 본문 재전송, SQS send-only |
| [로컬 예제](../examples/w4_question_core_local.py) | --contract w1-candidate 경로, 합성 context/policy·모의 queue·실제 프로세스 종료 |
| [후보 테스트](../tests/test_question_core_candidate.py) | 신규14개: 원문 hash·schema 호환·의미 정책·전송 차단·재시작 |
| [fixture 생성](../scripts/prepare-question-core-candidate-fixtures.py) | 고정 후보 원문으로 정상·거부·정책·digest 자료 재현 |
| [producer 검증](../scripts/verify-question-core-producer.py) | 공통+후보73개와 별도 후보 재시작 시연 |
| [압축 스크립트](../scripts/package-question-core-candidate.py) | 현재 검사 당시 source hash·문서 링크·ZIP CRC·manifest 검증 |
| [host 실행 안내](w4-question-core-producer.md) / [CT-12 준비표](w4-question-core-ct12-runbook-draft.md) | 실제 adapter/identity/volume 설정과 공동 실행의 남은 조건 |

ZIP에는 import 의존성을 충족하는 epick_w4 전체, 샘플·스키마·테스트·잠금 파일과 증거를 포함한다.
00-START-HERE.md와 SOURCE-STATE.json을 먼저 읽고 MANIFEST.json으로 파일 hash를 검증한다.
후보 원문의 내부 specs/** 링크는 W1 작성 환경 참조이며 이번 ZIP의 실행 의존성이 아니다.
자격증명·모델 가중치·가상환경·Git metadata·실행 DB는 전달물에 포함하지 않는다.

## 실제 검증의 범위

- [producer 73개와 후보 복구 시연](../output/question-core-candidate-20260919/local/summary.json): 실패·오류·skip0, 실제 SQLite/프로세스 종료·복구, 모의 queue.
- [전체 회귀 및 가상 HTTP 결과](../output/question-core-candidate-20260919/full/summary.json): **454개 통과, 실패·오류·skip0**. 가상 HTTP 시연2개·모의 모델 호출12회도 통과. 실제 모델 호출0.
- [상태 이미지](inputs/w1-runtime-status-reported-20260919.png)의 W1·AWS 완료는 팀 보고이며 이번에 직접 검증하지 않았다.
- 실제 SQS·W1 인증 context·IAM·PostgreSQL·공동 CT-12·LLM 호출·원격 CI는 미실행.

W4가 후보를 기술적으로 수용했다는 회신과 양측 채택·운영 승인은 구분한다.
P2/P3 운영 승인자는 팀에서 지정해야 하며 REAL과 후보 버전의 실제 전송은 계속 비활성이다.

## W1에 보낼 짧은 문안

> 후보 원문 2개를 확인했고 SHA-256이 전달서와 모두 일치했습니다. 추가 원문 요청은 없습니다.
> A1/P1–P3/T1–T5 원문 양식의 항목별 회신과 후보 schema를 그대로 사용하는 W4 codec·fixture·로컬 검증 자료를 첨부합니다.
> type:null 호환 문제는 W4 codec에서 수정했고 W1 schema 변경 요청은 없습니다.
> P2/P3의 운영 정책 승인자·활성화 조건, 최종 운영 version·body 상한·공통 digest/fixture 합의를 확인 부탁드립니다.
> 이후 양측 commit/SHA·image와 W1 인증 context·W4 queue/role/SenderId를 연결해 공동 CT-12를 진행하겠습니다. 현재 자료는 실제 전송·공동 검증 완료 자료가 아닙니다.

위 문안과 회신은 미발송 초안이다.
