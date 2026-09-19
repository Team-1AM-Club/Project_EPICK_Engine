> 2026-09-20 후속: [HTTP runtime r5](w4-http-runtime-handoff-2026-09-20.md)가 실행 환경·context 계약 미정 상태를 대체합니다. 아래는 r4 당시 기록입니다.

# W4 실제 runtime 인계 요청 검토·회신 · 2026-09-19 r4

[W1 요청 원본](inputs/W1_W4_Actual_Runtime_Handoff_Request_2026-09-19.md)의 필수 양식을 기입했다.
**현재 PENDING**이다. 로컬 wire 호환 수정은 완료했지만 실제 W4 runtime·image·sender identity·격리 SQS 증거는 아직 없다. 미발송 W4 회신이다.

W1 기준 commit `519b9127227ad3ca6483a61a5143d355c5eea5eb`의 원본을 확인했다.
[W1 계약 README](../samples/question-core-w1-runtime-20260919/W1-CONTRACT-README.md)는 wire shape 채택을 명시하며, runtime/정책 활성화와 구분한다.
W1 adopted schema SHA-256은 `1d004ea5ea4bbd346926c6be878de759f25b43011b7117ff8700c4d48e8b71af`다.

```text
# W4 → W1 Question Core actual runtime handoff

status: PENDING
W4 repository/access path: https://github.com/Team-1AM-Club/Project_EPICK_Engine (아래 신규 변경은 로컬 검증본)
W4 producer/outbox/relay full SHA: PENDING — A1. 현재 base d9e31822e2a031b41a303f05ad1e96d29fa09d8f에는 새 producer 미포함; 신규 commit/push 없음
W4 adopted schema path: PENDING — A2. 로컬 원본 경로 samples/question-core-w1-runtime-20260919/question-core-decision.event.schema.json; W1 wire 채택 원본은 확보했으나 W4 tracked commit 없음
W4 valid/negative fixture paths and canonical digest vectors: PENDING — A3. 로컬 samples/question-core-w1-runtime-20260919/{valid-core.json,valid-non-core.json,negative-events.json,digest-vectors.json}; W4 tracked commit 없음

## A. Reproducible producer
commit verification command and result: PENDING — A1. git rev-parse HEAD = d9e31822e2a031b41a303f05ad1e96d29fa09d8f; git cat-file -e HEAD:epick_w4/question_core_producer.py = 해당 경로 HEAD에 없음. W1 원본은 519b9127227ad3ca6483a61a5143d355c5eea5eb에서 git show로 확보·hash 검증
included producer/outbox/relay paths: epick_w4/question_core_producer.py, epick_w4/question_core_outbox.py, epick_w4/question_core_relay.py 및 epick_w4/question_core_contract.py — 로컬 ZIP 포함; 접근 가능한 commit 포함 여부는 A1 PENDING
candidate-to-adopted compatibility and unsent-outbox handling: W1 adopted 원본은 후보와 title/직렬화 byte만 다르고 검증 의미와 wire version은 동일. 정확한 W1 commit/schema hash에만 기존 candidate 문자열 전송 금지의 예외를 추가. 기존 candidate outbox를 새 schema로 열면 CORE_SCHEMA_CHANGED로 차단하며 ID/body/digest를 바꾸지 않음. 기존 자료는 합성 테스트용이며 실제 runtime은 새 단일 호스트 volume에서 시작. 다른 운영 미전송 데이터의 자동 migration은 구현하지 않음

## B. Immutable runtime image
image reference: PENDING — B1. 실제 빌드·registry·배포 대상 미확정
immutable image digest: PENDING — B1. 실제 image 빌드/게시하지 않음
image start/restart verification command and result: PENDING — B1. container 기동 검증 미실행; 로컬 Python/SQLite 재시작 결과로 대신하지 않음
persistent volume/store and recovery boundary: LOCAL_VERIFIED: 단일 호스트 로컬 SQLite WAL/FULL, immutable body/ID·lease 기반 복구. 배포 volume/보존·복구 설정은 PENDING — B2. 동작 중 DB를 Drive·복수 PC가 공유하는 방식 미지원

## C. Authenticated W1 context and currentness
W1 context adapter path: PENDING — C1. epick_w4/question_core_producer.py의 W1ContextPort는 내부 Protocol이며 실제 W1 서비스 인증 adapter가 아님; 합성 구현은 examples/w4_question_core_local.py
trusted input fields accepted from W1: PENDING — C1. 로컬 port 요구 필드명: context_key, job_id, question_version_id, source_id, analysis_input_version, authorization_revision, current_decision_version, data_kind, processing_allowed, question_current, source_active, revoked, valid_until. 실제 W1 owner/deletion epoch·fence/lease와의 결속·전달 형식은 미합의
send-time checks: LOCAL_VERIFIED: exact Job/question/Source/input binding, authorization_revision 변경, decision cursor, cancel/revoke/active flags, context 만료, outbox lease. owner/deletion epoch·W1 fence/lease를 인증된 최신 값에 결속하는 실제 adapter는 PENDING — C1; outbox lease를 W1 실행 fence로 대체하지 않음
revocation/cancel/delete/stale test command and result: LOCAL_ONLY: python scripts/verify-question-core-producer.py --contract w1-adopted --output-dir output/runtime-local-new → 이번 output/question-core-runtime-readiness-20260919/local-final/summary.json 85 PASS 및 실제 로컬 프로세스 복구 PASS. 실제 W1 취소/삭제/epoch/fence 변경 주입과 송신 차단은 PENDING — C2

## D. SQS identity — actual values via approved secure channel only
W4 send-only role delivery: PENDING — D1. 실제 workload role·발급 담당·승인된 안전 채널 미제공; 값/fingerprint/참조 ID 추정 없음
stable SenderId delivery: PENDING — D1. role의 실제 stable role ID 미확인·미전달; 세션 이름으로 대체하지 않음
send permission scope: 설계 범위는 SendMessage to dedicated W4 main queue only. 실제 IAM 정책·queue 결속 확인은 PENDING — D2
no-receive/no-delete/no-W1-DB-access confirmation: 코드에서는 send-only·W1 DB 접근 경로 없음 확인. 실제 workload IAM 권한·네트워크 접근 범위 확인은 PENDING — D2

## E. Actual isolated transport evidence
isolated runtime identity: PENDING — E1. 실제 격리 runtime/queue label 미제공
actual SQS send/retry/restart result: PENDING — E1. 실제 SQS 요청0. Stubber/Fake Queue 결과는 local/summary.json에만 기록; 실제 transport 증거 아님
same-id/same-body replay result: PENDING — E2. 로컬 재시도·프로세스 복구에서 동일 ID/body 확인; 실제 W1 durable receipt·SQS delete 결속 검증 미실행
same-id/different-body and revoked/stale rejection result: PENDING — E2. 로컬 immutable DB·digest/currentness 차단만 검증; 실제 W1 격리 queue/consumer와 altered replay·취소/삭제/stale 경계 실측 없음

## F. Policy and CT-12 readiness
P1 owner/revision/status: W4 기술 책임: W4 담당자 / 정책 승인 owner=PENDING, approved revision=PENDING, 기술 원칙 수용·운영 승인 대기 — F1. 합성 policy revision을 운영 승인 근거로 사용하지 않음
P2 owner/revision/status: W4 정의·구현 책임: W4 담당자 / 운영 승인 owner=PENDING, approved revision=PENDING, DISABLED — F1
P3 owner/revision/status: W4 reason 적용 책임: W4 담당자 / 운영 승인 owner=PENDING, approved revision=PENDING, DISABLED — F1
REAL user-data emission state: DISABLED
W4 CT-12 executor and teardown responsibility: W4 producer/outbox/relay 실행·자체 프로세스/테스트 DB 정리는 W4 책임. 실행 담당 실명·일정, W1 queue/DB·공용 AWS 자원 및 W2 검증/teardown 담당은 PENDING — F2; W1/W2와 runbook에 확정 필요
blocking condition and release condition for every PENDING item: A1~A3, B1~B2, C1~C2, D1~D2, E1~E2, F1~F2의 owner·blocker·해제 조건은 아래 표에 각각 기재. 모든 PENDING 표기는 이 ID 중 하나에 연결됨
```

## PENDING 항목별 해제 조건

| ID | 책임 owner | 현재 blocker | 해제 조건·제공할 근거 |
| --- | --- | --- | --- |
| A1 | W4 구현 담당자 | 기존 base에 producer가 없고 신규 코드·의존성·배포 범위 미커밋 | 관련 코드와 잠금 의존성·schema/fixture를 검토한 변경 범위로 commit/push; 원격에서 해당 full SHA와 파일을 조회·재현 확인 |
| A2/A3 | W4 구현 담당자, W1 계약 담당자 | W1 wire 원본은 확보했지만 W4 공유 commit에 없음 | 이번 pinned 원본·fixture와 codec을 A1 commit에 포함; W1과 공통 fixture/digest 대조. 원문 버전 이름을 임의로 바꾸지 않음 |
| B1 | W4 배포 담당자(실명 PENDING), 실행 환경 제공 측 | host/아키텍처·빌드 도구·registry·실제 context/policy adapter 미확정 | 환경·registry·adapter와 A1 source pin 준비 후 image build/start/restart 실행, 실제 digest 제공. 확인한 Windows PATH/표준 경로에서는 Docker/Podman을 발견하지 못했으며 전체 설치 여부를 단정하지 않음 |
| B2 | W4 배포 담당자 | 배포 volume·재기동 보존 설정 미확정 | 단일 host 영속 volume과 접근 제어·재기동 복구 설정을 확정하고 image 재시작으로 검증 |
| C1 | W1 context 공급 담당자 + W4 adapter 구현 담당자 | 확인한 W1 API/router/Job 응답 및 대상 코드 검색에서 W4 서비스 인증·currentness 전달 계약을 찾지 못함. 현재 Job 조회 응답은 owner/deletion epoch·authorization revision·fence/lease 결속을 제공하는 W4 계약으로 확인되지 않음 | 서비스 간 인증 방식·scope, W1-issued Job/context 전달/조회 방식, 필드·버전·epoch/fence/만료/오류 의미를 W1이 제공하고 W4가 실제 adapter 구현. 새 receipt ACK API 요구가 아님 |
| C2 | W4 실행 담당자 + W1 상태 변경 담당자 | 실제 adapter·격리 W1 상태 주입 방법 미제공 | 실제 취소·삭제·owner epoch·input/fence 변경을 주입하고 매 send 전 차단 확인; 마지막 검사 후 경쟁 변경은 W1 consumer의 원자 재검사로 공동 확인 |
| D1 | W4 workload IAM 발급 담당자 + W1 AWS 담당자(실명 PENDING) | 실행 환경·실제 workload role/stable ID·안전 채널 미확정 | workload Role과 stable SenderId를 담당자가 확인하고 승인된 안전 채널로 전달. 문서에는 수신 확인 참조/fingerprint만 기록 |
| D2 | W4 IAM 담당자 + W1 queue 담당자 | 실제 queue 및 양측 최소 권한·expected sender 결속 미검증 | 격리 main queue에 SendMessage만 부여하고 receive/delete/W1 DB 접근 권한 부재를 실제 정책으로 확인 |
| E1 | W1 AWS 담당자(격리 queue) + W4 실행 담당자 | 요청서 §4는 A–F 수령 후 queue 생성, E는 그 queue의 실제 결과를 선행 요구. 별도 기존 시험 queue도 미제공 | A/B/C/D 준비·F 제한 기록 → W1 격리 queue/IAM 준비 → W4 실제 송신/복구 E → 공동 CT-12 순서로 조정하거나, 먼저 사용할 별도 승인된 격리 queue 지정 |
| E2 | W4/W1 실행 담당자, W2 경계 담당자 | E1 환경과 W1 consumer/DB 조회·변경 주입 runbook 미확정 | commit-before-send·응답 유실·restart·동일/변조 재전송·revoked/stale의 실제 SQS/W1 receipt/delete 결과, user retry 이전 W2 command 0건을 기록 |
| F1 | W4 정책 정의/적용 담당자 + 팀이 지정할 운영 정책 승인자 | P1/P2/P3의 실제 owner·approved revision·승인 사례 미제공, 운영 policy adapter 미구현 | owner·정책 revision·의미/허용 reason·검토 사례를 승인하고 adapter 구현·검증. 미승인이면 DISABLED 유지; 합성 CT-12 범위와 REAL 활성화는 별도로 결정 |
| F2 | W4 실행 담당자 + W1/W2 공동 담당자 | 실제 executor·일정·공용자원 teardown 책임 미확정 | runbook에 담당·격리 리소스·주입/조회 명령·보존/삭제 범위·정리 증거를 합의. 이번 준비표로 공동 실행을 완료 처리하지 않음 |

## W1 source 대조와 이번 수정

- 원본 schema·후보 사본·README·fixture/digest 총7파일을 지정 commit에서 받아 byte hash를 기록했다. [출처](../samples/question-core-w1-runtime-20260919/source-provenance.json).
- adopted schema와 후보의 JSON 차이는 설명용 title뿐이다. 직렬화 byte가 달라 schema hash는 다르지만 필드·제약·wire version은 같다.
- 기존 W4는 version 문자열에 candidate가 포함되면 무조건 거부해 `CORE_TRANSPORT_NOT_ADOPTED`가 발생했다. 확인된 W1 commit+schema hash 쌍에만 예외를 주도록 codec을 수정했다.
- 원래 후보 파일, 다른 commit, 다시 직렬화한 파일, 미승인 status는 SDK 생성 전에 계속 거부한다. default send=false·REAL/미승인 policy 차단도 유지한다.
- 기존 candidate outbox의 schema hash를 바꾸지 않는다. 새 계약으로 열면 차단하며 body/ID를 보존한다. 실제 운영 미전송 자료에 대한 자동 migration은 제공하지 않는다.

## 실제 검증과 한계

[관련85개와 로컬 복구](../output/question-core-runtime-readiness-20260919/local-final/summary.json) · [전체466개](../output/question-core-runtime-readiness-20260919/full-final/summary.json) · [원본·호환성·상태 점검](../output/question-core-runtime-readiness-20260919/readiness-verification.json).
신규12개 포함 관련85개와 전체466개 모두 실패·오류·skip0이다. 로컬 SQLite/프로세스 종료·재시작 및 합성 HTTP2개도 통과했다.
85개와466개는 중복을 포함하므로 합산하지 않는다. 실제 AWS·W1 인증 context·IAM·PostgreSQL·공동 CT-12·LLM·원격 CI는 이번에 실행하지 않았다.
[코드·파일 전달 안내](w4-actual-runtime-handoff-guide-2026-09-19.md).
