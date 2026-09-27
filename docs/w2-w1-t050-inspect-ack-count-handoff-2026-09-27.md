# W2 → W1: T050 삭제 v2 count-only inspect 인계

기준: W1의 [삭제 운영 입력 회신](https://github.com/Team-1AM-Club/Project_EPICK_Service/blob/d0ff44f8287305ed379ba6cfaa1fc403c0f875c2/md/deploy/W1_W2_T050_Deletion_Runtime_Inputs_Response_2026-09-27.md)과 `backend/infra/w2-deletion-runtime-inputs.template.json`. 이 문서는 W2의 로컬 구현·운영 의미를 고정하며 실제 AWS/W1 공동 실행 또는 T050/T058 완료를 뜻하지 않습니다.

## Count-only 계약

`python -m epick_engine.source_collection.private_deletion_operator_v2 inspect`는 `preflight`를 통과한 뒤 다음 두 **음이 아닌 정수**만 JSON으로 출력합니다. owner ID, 삭제 payload, token, URL은 출력하지 않습니다. 오류 시 count를 0으로 대체하지 않고 비밀값 없는 실패 상태와 nonzero exit code를 반환합니다.

| 필드 | 의미 | 정확도 |
| --- | --- | --- |
| `pending_deletion_count` | W1 전용 main SQS queue의 `ApproximateNumberOfMessages`(visible)와 `ApproximateNumberOfMessagesNotVisible`(in-flight)의 합. DLQ·delayed 메시지는 포함하지 않음 | SQS 제공 근사치이며 생산·소비 중 즉시 일치하지 않을 수 있음 |
| `pending_ack_count` | W2 PostgreSQL의 `w2.private-deletion.v2` 영속 receipt 중 W1의 정확한 `200 ACKNOWLEDGED` 확인 기록인 `ack_confirmed_at`이 없는 건수. v1 receipt 제외 | 해당 DB 조회 시점의 정확한 **W2 확인 미완료 건수**. W1의 실제 미완료 target 건수와 동일하다고 주장하지 않음 |

`inspect`는 main queue의 ARN·redrive·SSE, DLQ의 ARN·SSE 및 읽기 권한, DB 연결과 정확한 migration head를 검사합니다. 실제 consumer 프로세스 생존은 배포 supervisor가 별도로 확인합니다. SQS 메시지 수·W2 receipt 수는 서로 다른 시점과 저장소에서 얻으므로 둘의 합이나 차를 일관된 트랜잭션 수로 해석하지 않습니다. AWS는 두 SQS 속성이 근사치이며 생산 중단 후에도 최소 1분 동안 일관되지 않을 수 있다고 설명합니다: [GetQueueAttributes](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_GetQueueAttributes.html).

## ACK 기록과 복구 경계

새 nullable `private_deletion_receipts.ack_confirmed_at`은 migration `0013_deletion_ack_confirmed`에서 추가됩니다. 기존 v2 receipt는 성공을 추정해 backfill하지 않고 NULL, 즉 W2 확인 미완료로 남깁니다. W2 삭제 DB transaction을 commit한 다음 W1의 단일 purge+ACK callback이 `200 ACKNOWLEDGED`를 반환한 경우에만 W2가 별도 DB transaction으로 확인 시점을 저장합니다. 이 저장까지 성공해야 consumer가 SQS 메시지를 삭제할 수 있습니다.

W1 callback 실패·timeout 또는 W2 확인 기록 commit 실패 시 W2 receipt는 남고 메시지는 삭제되지 않습니다. 같은 command가 재전달되면 W2는 DB 삭제를 반복하지 않고 `DUPLICATE` ACK를 W1에 재시도합니다. 이미 더 높은 owner epoch가 들어온 `STALE`은 기존 계약대로 callback하지 않습니다. 특히 W1이 ACK 직후 다음 epoch를 시작하고 W2의 확인 기록이 실패한 경우, 이전 receipt의 미확인 건수와 DLQ가 수동 조사 대상이 될 수 있습니다. 이 값을 임의로 0으로 보정하거나 receipt를 무검증 완료 처리하지 않습니다. W1·W2의 target/receipt/ACK를 대조해 승인된 절차로 조정해야 합니다.

## 배포·공동 검증 선행 조건

1. W1은 W2 workload role 및 queue policy에 main queue와 DLQ의 읽기 전용 `sqs:GetQueueAttributes` 권한이 있는지 확인해야 합니다. `inspect`는 DLQ 메시지 본문을 읽거나 redrive하지 않습니다. DLQ ARN은 main queue의 검증된 redrive metadata로부터 확인합니다.
2. W2 DB를 `0012_private_ack_wire_digest`에서 `0013_deletion_ack_confirmed`로 **선행** migration하고 새 W2 immutable image를 배포해야 합니다. commit-gate, source runtime, 삭제 operator의 exact-head preflight가 모두 0013으로 갱신되었습니다. 이전 이미지는 새 head와 호환된다고 주장하지 않습니다. 다운그레이드는 지원하지 않으며 문제가 생기면 forward corrective migration을 사용합니다.
3. W1은 잠정 W2 source pin `3700b8dc324b4a365b19214550bd66b74171870b`를 새 W2 full SHA와 immutable image digest로 교체하고, W1 측 이미지도 pin해야 합니다. 실제 운영값은 승인된 SSM/Secrets Manager 경로로만 주입하며 이 문서에 쓰지 않습니다.
4. 격리 환경에서 `inspect` 두 필드와 main/DLQ 접근, `APPLIED`·`DUPLICATE`·`STALE`, 409/503/timeout, restart/redelivery, 60초 visibility/DLQ, W1 target/ACK·W2 receipt 수를 공동 기록해야 합니다. 이 증거 전에는 production 삭제 라우팅을 활성화하지 않습니다.

RenderedCollector와 robots/권리 gate는 이 작업과 별개로 미완료입니다. 한화인에는 `Disallow: /` 및 운영자 예외 허가 부재로 수집 요청을 보내지 않습니다.

## 로컬 검증 (2026-09-27)

- 격리 PostgreSQL을 사용하는 삭제·operator 관련 집중 회귀 204건 통과. 신규 migration에서 기존 v2 receipt를 확인 미완료로 보존하는지, W1 callback 실패·성공·재전달과 W2 확인 기록 실패 후 재시도를 확인했습니다.
- 전체 `pytest`: **2,164 passed, 8 failed, 1 skipped, 4 warnings**. 실패 8건은 모두 미구현 `RenderedCollector`의 기존 safety gate이며 이번 삭제/inspect 변경의 회귀는 아닙니다. 실제 브라우저 검증 1건은 승인된 대상·의존성·외부 접근 gate가 없어 skip입니다.
- Ruff check/format, `mypy src`(39 files), Alembic head `0013_deletion_ack_confirmed` 확인. 실제 AWS SQS, W1 private ACK endpoint, immutable image digest 및 공동 end-to-end 실행은 **미검증**입니다.
