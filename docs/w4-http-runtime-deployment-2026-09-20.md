# W4 Question Core CT-12 실행 안내

[인계 회신·W1 수정 요청](w4-http-runtime-handoff-2026-09-20.md).
이 문서는 W1 staging private Worker EC2에서 실행할 준비 사항이다. 현재 PC에 Docker/AWS 자원을
설치하거나 생성했다는 뜻이 아니다. 실제 값은 W1 안전 채널에서만 전달한다.

## 고정 소스와 이미지

전달한 full SHA를 checkout하고 `git rev-parse HEAD`가 일치하는지 확인한다.
`uv sync --locked --extra api --extra test` 후 다음 로컬 검증을 재현한다.

```sh
python scripts/verify-question-core-producer.py --contract w1-adopted --output-dir output/ct12-local-check
python scripts/verify_service_handoff.py --output-dir output/ct12-full-check
```

의존성은 `uv.lock`에서 export한 `deploy/question-core/requirements.lock`을 hash 검증하여 설치한다.
재생성 명령은 `uv export --frozen --no-dev --extra transport --no-emit-project --output-file deploy/question-core/requirements.lock`.
Dockerfile 기반 Python 3.12.14-slim-bookworm은 registry manifest digest로 고정했다.
빌드 context allowlist는 소스·adopted fixture·locked requirements만 포함한다.

```sh
docker build --build-arg W4_SOURCE_SHA="$(git rev-parse HEAD)" -f deploy/question-core/Dockerfile -t "$W4_BUILD_TAG" .
```

`W4_BUILD_TAG`와 ECR push 권한은 W1 provisioning 후 받는다. push 후 조회한
`repository@sha256:...`를 `W4_IMAGE_REF`로 지정한다. 태그만 주면 runtime에서 거부한다.
local image ID/기반 Python digest와 배포 W4 ECR digest를 혼동하지 않는다.

## W4 전용 설정과 파일

필요한 변수명은 [설정 목록](../deploy/question-core/env.names.md)을 따른다.
W1 env/DB 설정 파일을 재사용하지 않고 W4 전용 root-owned env 파일을 만든다.
`W4_SQS_SEND_ENABLED` 기본은 꺼짐이며 C1 수정·W1 provisioning·preflight 후에만 `true`로 둔다.

`W4_CT12_PLAN_DIR/plan.json`: W1이 실제 발급한 context UUID와 합성 시나리오별 submission_key,
명시적으로 검토한 decision version/code/reason/policy revision을 넣는다. Job/owner/source ID나
원문을 넣으면 schema가 거부한다. 예시는 `samples/question-core-w1-context-20260919/plan.json`이며
기본 미승인이다. 한 plan에는 context당 한 결정만 둔다. 새 version은 새 submission key를 쓴다.

W1 호스트의 AssumeRole 결과 중 다음 항목만 `W4_AWS_SESSION_DIR/session.json`으로 변환한다:
`Version`(정수 1), `AccessKeyId`, `SecretAccessKey`, `SessionToken`, `Expiration`(timezone 있는 RFC3339).
W1 원래 역할의 credentials는 기록하지 않는다. W4 전용 role session만 사용한다.
W4는 ASIA temporary access key와 session token을 요구하며 만료까지 30초 이하이면 전송하지 않는다.

W1 호스트가 만료 전에 같은 디렉터리에 임시 파일을 만들고 atomic rename하여 회전한다.
디렉터리 자체를 read-only bind하므로 교체된 파일을 다음 전송에서 읽는다.
호스트 파일은 root 소유·GID 10001 읽기만(예: 0440), 디렉터리는 root:10001 0750으로 설정한다.
이 경로에는 이 W4 세션만 둔다. 임의의 W1 credential 디렉터리를 통째로 mount하지 않는다.

W4는 각 SendMessage에 위 credentials를 명시적으로 전달한다. SDK credential chain·AssumeRole·IMDS를
사용하지 않는다. W1 host에서도 container subnet의 IMDS 접근을 차단한다. 실제 권한은 role trust,
SQS queue policy, dedicated main queue의 `sqs:SendMessage`만 허용하는 identity policy로 검증한다.
[STS AssumeRole](https://docs.aws.amazon.com/cli/latest/reference/sts/assume-role.html)과
[EC2 metadata 접근 제한](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-metadata-limiting-access.html)을 참조한다.

## 준비·실행·복구

Compose 실행 전 `worker_default` network, W1 private context service, root-owned W4 env,
검토한 plan, 회전 중인 W4 STS 파일, immutable `W4_IMAGE_REF`를 준비한다.
구성 출력으로 비밀이 노출되지 않도록 `config`는 `--quiet`로 실행한다.

```sh
docker compose -f deploy/question-core/compose.yaml config --quiet
docker compose -f deploy/question-core/compose.yaml run --rm w4-question-core check
docker compose -f deploy/question-core/compose.yaml run --rm w4-question-core prepare
docker compose -f deploy/question-core/compose.yaml up -d
```

`check`는 네트워크를 호출하지 않는다. `prepare` 성공 후 DB에 commit된 event가 생긴다.
relay는 재기동 때도 같은 volume에서 claim하고 W1을 다시 조회한 후 전송한다.
`SENT / TRANSPORT_ACCEPTED_ONLY`는 SQS 수락만 의미한다. W1 durable receipt/최종 처리 완료와 다르다.

401/403이면 프로세스가 종료된다. config/secret 교체 전 자동 재기동하지 않는다.
503/timeout·SQS 응답 불확실은 기존 body/ID를 유지한 backoff retry다.
blocked 행은 자동 부활하지 않는다. W1과 상태를 대조하고 새로 승인된 context/submission/version으로
진행해야 한다. candidate DB의 event를 adopted 형식으로 직접 수정하지 않는다.

복구 검증은 container만 중지·재생성하고 named volume을 유지한다.
최종 CT-12 증거 승인 전 `down -v` 또는 volume 삭제를 하지 않는다.
응답 유실 fault injection·실제 W1 receipt·W2 command 결과는 공동 runbook에서 각 담당자가 수집한다.
로컬 fake queue를 실제 전송 증거로 기록하지 않는다.

## 실행 전 남은 확인

W1 owner epoch 누락 수정 및 실제 DB 회귀 검증, ECR/role/queue/context 발급, stable SenderId 결속,
실제 private DNS/네트워크·파일 권한·IMDS 차단, source/image digest 대응, CT-12 실행자·teardown 담당 확정.
P2/P3 운영 승인과 REAL 자료 전송은 이번 합성 시험에 포함하지 않는다.
