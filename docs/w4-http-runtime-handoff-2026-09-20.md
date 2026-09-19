# W4 → W1 HTTP Context·실행 구성 인계 · 2026-09-20 r5

새 W1 기준: `deda25c62a762e3f7f6ea5273c93a7e6a18c6412`.
이 회신은 9월 19일 r4의 “실행 환경·HTTP 계약 미정”을 대체한다.
W4 구현과 로컬 검증을 제공한다. 실제 W1 서버·AWS·공동 CT-12의 완료 증거는 아니다.

## A. 재현 가능한 producer

저장소: https://github.com/Team-1AM-Club/Project_EPICK_Engine

브랜치: `feat/w4-question-core-runtime`. 전달 ZIP의 `SOURCE-STATE.json`과 별도
`W4-TRACKED-SOURCE.json`에 push 후 확인한 실제 full SHA·CI 실행을 기록한다.
코드와 검증 대상의 full SHA를 확인한 뒤 W1 provisioning을 진행한다.

| 경로 | 기능 |
| --- | --- |
| `epick_w4/question_core_http.py` | 고정 private URL·W4 bearer·principal로 W1 context를 매번 조회. 닫힌 schema·UUID·opaque hash 검증. redirect/proxy 차단. |
| `epick_w4/question_core_runtime.py` | 실행 진입점, 명시적으로 검토한 SYNTHETIC 계획, W4 전용 임시 자격증명 연결. |
| `epick_w4/question_core_producer.py` | W1이 제공한 ID로만 결정 작성. prepare/send 때 상태·revision·정책 재검증. |
| `epick_w4/question_core_outbox.py` | SQLite WAL 영속 저장, immutable body, lease·재전송·차단. |
| `epick_w4/question_core_relay.py` | 매 전송 직전 재검증 후 `SendMessage` 1회. SDK 자동 재시도 없음. |
| `samples/question-core-w1-context-20260919/` | W1 원본 schema·valid/negative fixture·digest vector·원문 코드·출처 hash와 미승인 계획 예시. |
| `deploy/question-core/` | digest로 고정한 Python 기반 Dockerfile, hash 고정 의존성, private network Compose, 변수명 안내. |
| `tests/test_question_core_http.py`, `tests/test_question_core_runtime.py` | 실제 loopback HTTP, 오류·재시작·상태 변경, plan 철회, 임시 자격증명 회전 테스트. |

W1 adopted schema bytes와 hash는 r4와 동일하다. version 문자열의 `candidate` 표기는 W1
원문 그대로 유지한다. 최초 후보 schema를 쓴 미전송 outbox는 자동 변환하지 않고 차단한다.
r4 adopted schema로 만든 기존 outbox는 호환 schema hash를 유지하되, 실제 context가 달라지면 차단한다.

## B. 이미지·실행·영속성

이미지 구성과 진입점은 제공 완료. **ECR image reference/digest·staging 기동/복구는 PENDING**.
W1이 이 SHA로 ECR repository/권한을 만든 다음 빌드·push하여 실제 digest를 고정한다.
GitHub CI의 local image ID가 나오더라도 ECR 배포 digest나 staging 검증을 대신하지 않는다.

진입점: `python -m epick_w4.question_core_runtime`.
명령: `check`(로컬 설정·SQLite만), `prepare`(HTTP 조회·outbox 저장),
`relay-once`(대기 1건), `relay`(5초 간격 전송 처리).
`check` 성공은 HTTP/AWS 접속 성공이 아니다. `prepare`는 SQS에 보내지 않는다.

UID/GID `10001:10001`, `/var/lib/w4/outbox.sqlite3`, 전용 volume `epick-w4-ct12-outbox`.
DB 파일만 복사하지 않고 동일 volume과 WAL을 함께 보존한다. 살아 있는 DB를 Drive/NFS에 두지 않는다.
private external network `worker_default`, W1 DNS `w1-w4-question-core-context:8081`.
public API/host port 없음. 인증 실패 후 운영자가 설정을 바꾸기 전 자동 restart 없음.

상세 명령·권한·전달 변수는 [실행 안내](w4-http-runtime-deployment-2026-09-20.md)를 따른다.

## C. W1 인증 context·현재성

`POST /internal/v1/w4/question-core-contexts/resolve`와
`w1.private.w4-question-core-context.v1`을 원문대로 채택한다.
입력은 W1-issued `context_key`만 받고 job/source/question ID는 응답에서만 가져온다.
매 prepare·send·재시작 후 첫 send에 resolve한다. 성공 응답을 cache하지 않는다.

`processing_allowed=false`, revoke, 질문/Source 무효, 만료, REAL, opaque
`authorization_revision` 또는 결속값 변경은 저장/전송을 차단한다.
401/403은 adapter를 잠그고 relay를 종료한다. secret/config를 교체해 재기동해야 한다.
404/422는 해당 outbox를 terminal blocked로 둔다. 503·timeout은 lease/backoff 이후 동일 body/ID만
다시 시도한다. 인증 실패로 이미 blocked된 행은 자동 복구하지 않는다. W1과 상태를 확인한 뒤
유효 context 및 새 submission/version으로 명시적으로 재개한다.

owner deletion epoch·fence·lease는 W1만 볼 수 있다. W4는 opaque revision과 flags로 차단하며,
수신 후 W1 locked transaction이 최종 재검증한다.

### C1. W1에 수정·DB 검증 요청

W1 원문 `backend/app/runtime/w4_question_core_context.py`의 `revoked`는
`job["owner_deletion_epoch"]`를 context와 비교하지만 현재 `owner["deletion_epoch"]`는 비교하지 않는다.
따라서 owner epoch만 증가하고 다른 조건이 유지된 합성 상태에서는 첫 조회가
`revoked=false, processing_allowed=true`다. 문서의 “deletion epoch 변경 시 false”와 다르다.

원문 AST의 해당 두 식만 합성 값으로 실행하여 재현했다. 실제 PostgreSQL 재현은 **NOT_RUN**.
이전 응답을 저장한 outbox는 opaque hash 변경으로 차단되지만 **변경 이후 처음 prepare**하는
경우에는 비교할 과거 hash가 없다. W4가 삭제 epoch 원값을 추측해 보완할 수 없다.

제안: `revoked`에 `or owner["deletion_epoch"] != context.owner_deletion_epoch`를 추가하고,
DB 테스트로 owner epoch 단독 변경·Job epoch 변경·lease·취소·삭제를 확인한다.
W1 저장소를 임의 변경하지 않았다. 수정 SHA와 DB 검증을 받은 후 실제 CT-12 send를 활성화한다.
재현: `python scripts/review-w1-context-boundary.py --output output/w1-epoch-review.json`.

## D. AWS identity

실제 role/SenderId/queue 전달: **PENDING — W1 provisioning 이후**.
W1 호스트가 W4 전용 역할을 AssumeRole한다. W4에는 결과인 임시 credentials만
읽기 전용 디렉터리로 주고, 각 전송마다 새로 읽는다. W1 EC2 자격증명을 container에 주지 않는다.
W4는 credentials가 누락·만료되면 SDK 기본 체인/IMDS로 fallback하지 않는다.

애플리케이션 호출은 `SendMessage`뿐이다. **실제 IAM의 receive/delete/purge/DB 접근 금지는 미검증**이며
W1의 role·queue policy·host IMDS 차단 preflight로 확인한다. 환경변수로 IMDS를 끄는 것은 네트워크
격리를 대신하지 않는다. Role ARN/SenderId/Queue URL/secret은 문서와 로그에 적지 않는다.

## E. 실제 전송 증거

actual W1 authenticated request / actual SQS send / ECR image / stable SenderId / 공동 CT-12:
**PENDING 또는 NOT_RUN**. 로컬 HTTP와 mock SQS를 실제 AWS 증거로 취급하지 않는다.

로컬 테스트는 false·만료·revision/input 변경 시 무전송, 불확실한 송신 뒤 같은 body/ID 재전송,
503 뒤 재조회, 프로세스 재시작, 인증 실패 중단, operator plan 철회, STS 결과 회전을 확인한다.

## F. 정책·다음 순서

P1: W1 발급 ID와 QUESTION_MATCHING 결속·기술 계약 채택. 역할 책임은 W4 producer / W1 inbound.
명명된 팀 정책 승인자·최종 운영 revision은 별도 합의 기록을 따른다.
P2/P3: 운영 의미 판단 승인자·revision **PENDING**, REAL 발행 **DISABLED**.
합성 CT-12 결정만 operator가 검토한 plan에 `approved=true`로 표시한다.
이 값은 LLM 추천·사용자 운영 정책을 승인하지 않는다. 기본 plan은 `approved=false`다.

1. W4 tracked SHA·CI·배포 요구 제공.
2. W1은 C1 수정/DB 회귀 테스트와 함께 전용 ECR·격리 DB/context·role·main/DLQ 준비.
3. W1 안전 채널의 context key/설정과 임시 role credentials로 W4 이미지 빌드·기동, stable SenderId 결속.
4. 양측 image digest 고정, outbox volume 복구·응답 유실·중복·stale·취소/삭제·명시적 retry/W2 경계 CT-12.
5. W4는 자기 container·SQLite/송신 증거 수집과 중지를 담당. W1은 AWS/DB 자원 teardown,
   W2는 retry/command 경계를 검증한다. 실행자 실명·시간·teardown 승인자는 공동 runbook에서 지정한다.

단순 ZIP 제출이나 CI 통과로 `CT12_COMPLETE`, `W2_HANDOFF_READY`, REAL enablement를 해제하지 않는다.
