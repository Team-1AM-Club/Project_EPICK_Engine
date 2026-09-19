# W4 Question Core producer 로컬 구현 안내

상태: **W1 wire 채택 원본 pin·codec 호환 / 실제 로컬 DB outbox / default send=false·REAL 비활성**.
[실제 runtime 회신 r4](w4-actual-runtime-handoff-reply-2026-09-19.md)가 현재 전달 문서다. W1 commit 519b9127은 wire 채택의 근거이며 실제 연결·운영 정책 승인과 구분한다.

후보 원문 2개를 전달서에서 확보·검증했다. D01–D03 합의 후 채택 완료 SHA를 교환한다.
기존 W1 baseline과 candidate review checksum은 전송을 활성화하는 채택 증거가 아니다.

## 파일별 역할

| 파일 | 기능 |
| --- | --- |
| `epick_w4/question_core_contract.py` | 외부에서 명시한 schema의 SHA 확인, flat event 생성·검증, canonical JSON/digest. W1 version 상수를 추측하지 않음 |
| `epick_w4/question_core_producer.py` | host의 authenticated W1 context와 approved W4 policy를 결속해 새 결정 준비. REAL 차단, ID·시각 생성, 재시도/currentness 검사 |
| `epick_w4/question_core_outbox.py` | 결정·본문 원자 저장, 중복/충돌·immutable body, attempt/error/lease 및 재시작 복구 |
| `epick_w4/question_core_relay.py` | 전송 직전 currentness·lease 확인, 고정 main queue에만 SQS SendMessage, 확인된 acceptance 후 sent |
| `examples/w4_question_core_local.py` | 합성 context/policy와 가짜 queue. os._exit로 실제 프로세스 중단을 재현하는 로컬 전용 도구 |
| `tests/test_question_core_producer.py` | DB 원자성·동시 제출·중복·변조·철회·버전·재시작 테스트 |
| `tests/test_question_core_sqs.py` | 실제 boto3/botocore 모델을 Stubber로 검사. AWS 통신 없음 |
| `scripts/verify-question-core-producer.py` | 관련 검사와 별도 프로세스 복구 결과·소스 해시를 JSON으로 기록 |
| `scripts/verify-question-core-sources.py` | 제공받은 W2 pin의 checksum 검증, W1 원본 경로 존재 여부 및 generic digest helper pin 기록 |
| `scripts/prepare-question-core-local-fixtures.py` | 명시적인 TEST_ONLY fixture 생성. W1 원본으로 승격하지 않음 |
| `samples/question-core-local/` | 기존 TEST_ONLY fixture와 역사적 원본 탐색 기록 |
| `samples/question-core-candidate-20260919/` | 받은 W1 원문·checksum, 후보 정상2·거부/결속25·정책 경계·digest3개 |
| `tests/test_question_core_candidate.py` | 후보 원문·type:null 호환·정책/전송 차단·실제 프로세스 복구14개 |

## host 연결 경계

`QuestionCoreProducer`에 `QuestionCoreContract`, `QuestionCoreOutbox`, `W1ContextPort`, `W4PolicyPort`를 주입한다.
`prepare(submission_key=..., context_key=...)`의 두 key는 host가 소유하는 opaque 제출/문맥 식별자다.
public request/LLM 결과를 JobContext나 PolicyDecision으로 직접 변환해서는 안 된다.

W1ContextPort.load는 W1이 인증·권한·현재 관계를 확인한 결과를 반환해야 한다.
job_id, question/source/input, decision cursor, authorization_revision, 현재 상태, 유효기간이 필요하다.
authorization_revision에는 owner/project/company 관계·epoch/fence 변경이 반영되어야 한다.
이 Python 내부 port는 **새 W1 HTTP API 계약이 아니며**, 정확한 전달 방식은 W1과 합의 전이다.

W4PolicyPort.load는 현재 정책 revision과 명시적으로 승인된 Core/Non-Core 결정만 반환한다.
제품 승인 전 실제 사용자 자료 자동 발행은 차단한다. 모호한 판단은 미승인 상태 또는 안전한 거부로 반환한다.
LLM 추천 순위·SUPPORTED 또는 W3 USABLE을 Core로 자동 변환하지 않는다.

QuestionCoreRelay.run_once는 DB lease 획득 → fresh context/policy → immutable body 대조 → lease 확인 → send → sent 순서다.
`SENT`는 transport acceptance만 뜻한다. W1 receipt, 자료 수집 완료, W2 실행 재개나 결과 가시성을 의미하지 않는다.
마지막 검사와 W1 수신 사이의 관계 변경은 W1 consumer의 원자 재검사가 막아야 한다.

## DB 운영 전제

`QuestionCoreOutbox`에는 전용 DB의 절대 경로를 전달한다. 메모리 DB와 SQLite URI, 타 용도의 기존 DB를 거부한다.
현재 구현은 **한 호스트의 영속 로컬 volume**을 위한 SQLite WAL/FULL outbox다.
실행 중 DB를 Google Drive·네트워크 폴더에서 열거나 여러 PC가 동시에 공유하는 구성을 검증하지 않았다.
코드·문서의 프로젝트 동기화와 실행 중인 DB의 동시 공유는 별도다.

상태는 prepared/sent/blocked다. 전송 응답 유실 때 prepared와 body를 유지하고 backoff 후 재시도한다.
프로세스가 종료되면 lease 만료 후 다른 worker가 같은 body를 회수한다.
blocked 제출은 재승인만으로 되살리지 않는다. 새로 승인된 문맥·결정 revision에 대해 새 제출을 준비한다.
DB hash는 일관성 검사이고 인증 수단은 아니다. DB volume 및 host adapter의 접근 제어는 배포 책임이다.

## 안전한 설정 이름

아래는 host wiring에 사용할 이름이다. 현재 공개 endpoint나 환경변수만으로 시작되는 runtime CLI는 제공하지 않는다.
합의된 운영 schema·인증된 W1 port가 준비되기 전에는 standalone 발행기를 활성화하지 않기 때문이다.

| 설정 이름 | host에서 연결할 대상 |
| --- | --- |
| `W4_CORE_OUTBOX_PATH` | QuestionCoreOutbox의 영속 로컬 DB 절대 경로 |
| `W4_CORE_SCHEMA_PATH` | 수령·검토된 W1 원본 schema 파일 |
| `W4_CORE_SCHEMA_SHA256` | ContractSource.schema_sha256. 검토된 원본 바이트의 hash |
| `W4_CORE_W1_FULL_SHA` | 합의 뒤 채택된 flat schema를 확인할 W1 commit. 기존 baseline bb27a692…는 여기에 사용할 채택 근거가 아님 |
| `W4_CORE_MAIN_QUEUE_URL` | SqsSendSettings.main_queue_url. W4 전용 Standard main queue |
| `W4_CORE_MAIN_QUEUE_ARN` | SqsSendSettings.main_queue_arn. 위 URL의 account/region/name과 일치 |
| `AWS_REGION` | SqsSendSettings.region |
| `W4_CORE_SEND_ENABLED` | SqsSendSettings.enabled. 기본 false, 승인/환경 확인 후 host가 명시적으로 true 지정 |

adoption status는 배포 설정 검토에서만 W1_ADOPTED로 지정한다. 문자열을 바꾸는 행위가 팀 합의를 만들지는 않는다.
repository의 test-only 및 원래 candidate 원문은 해당 status로 재표시해도 실제 adapter에서 거부한다.
W1은 adopted schema에서도 candidate version 문자열을 유지했다. 확인된 commit 519b9127227ad3ca6483a61a5143d355c5eea5eb와 schema hash 1d004ea5ea4bbd346926c6be878de759f25b43011b7117ff8700c4d48e8b71af의 정확한 쌍만 예외로 허용한다. 원래 후보나 다른 commit/hash는 거부한다. 이 예외는 wire 호환이며 runtime·REAL 활성화 승인이 아니다.
fixture를 운영 schema로 이름만 바꾸거나 synthetic host adapter를 운영 인증으로 사용하는 것은 지원하지 않는다.

## Send-only IAM 범위

배포 담당자가 확인한 **W4 main queue ARN 한 개**만 다음 policy의 Resource에 넣어야 한다.
실제 ARN/role은 미제공이며 이 예시를 적용하거나 role을 생성하지 않았다.

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["sqs:SendMessage"],
    "Resource": "<W4_CORE_MAIN_QUEUE_ARN>"
  }]
}
```

다른 넓은 policy가 함께 붙어 있으면 이 예시만으로 최소 권한이 보장되지 않는다. 실제 IAM 검증은 공동 환경에서 한다.
W1 queue receive/delete, DLQ send, purge, W1 DB 권한을 W4에 요구하지 않는다.

adapter는 MessageId, HTTP 성공과 body MD5를 확인한다. MD5는 SQS 응답의 전송 일관성 검사이며 인증용 해시가 아니다.
[AWS SendMessage 응답 규격](https://docs.aws.amazon.com/boto3/latest/reference/services/sqs/client/send_message.html).
SDK의 `total_max_attempts=1`로 내부 재시도를 꺼서 매 application retry가 currentness 재검사를 거치게 한다.
[Botocore retry 설정](https://docs.aws.amazon.com/botocore/latest/reference/config.html).

## 검증과 남은 경계

```powershell
uv sync --locked --extra api --extra test
uv run --locked --extra api --extra test python scripts/verify-question-core-producer.py --contract w1-adopted --output-dir output/question-core-check-new
```

새 출력 폴더가 필요하다. 합성 자료만 쓰고 실제 SQS·LLM·W1 endpoint에는 접속하지 않는다.
재시작 시연은 OS 로컬 임시 디렉터리에서 실행하고 실제 프로세스 종료·복구를 확인한 뒤 임시 DB를 정리한다.
결과 JSON에는 fake queue임을 표시하고 actual_sqs_requests=0, joint_ct12=NOT_RUN을 남긴다.

W1 wire 채택 원본과 codec 호환을 확인했다. 실제 인증 context·운영 정책·배포/IAM 담당과 전달 계약을 확정하고, 검토된 코드/schema/fixture commit·image pin → 격리 queue/DB 준비 → 실제 송신·복구 → 공동 CT-12로 진행한다. 원문 버전 문자열을 임의로 변경하지 않는다.
기존 candidate outbox는 새 schema에서 CORE_SCHEMA_CHANGED로 차단하며 body/ID를 유지한다. 합성 검토 DB를 운영 DB로 승격하거나 schema hash를 덮어쓰지 않는다.
