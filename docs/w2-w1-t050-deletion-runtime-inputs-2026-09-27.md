# W2 → W1: T050 삭제 v2 운영 연결 입력 요청

기준: W1 Service `8d80a6f0edddd350a1e0308751fdb19bf7318d76`의 v2 dispatcher 및 인증된 `POST /internal/v1/w2-private/deletion/ack`. 이 문서는 이미 합의한 v2 payload/ACK schema, owner별 epoch 직렬화, W2 DB 선행 commit, W1 단일 transaction의 private purge+ACK를 다시 결정해 달라는 요청이 아닙니다.

W2가 확인한 경계: `PrivateDeletionCommandV2`, PostgreSQL receipt, SQS consumer, W1 ACK HTTP callback 및 전용 `private_deletion_operator_v2` CLI가 로컬에 구현되었습니다. W2는 별도의 W1 purge 호출을 만들지 않고, W2 DB commit 후 정확한 v2 ACK를 W1의 단일 callback으로 보냅니다. `STALE`에는 callback을 보내지 않습니다. 아래 운영 입력과 공동 검증이 확정되기 전에는 production 삭제 라우팅을 활성화하지 않습니다.

## W1 확인 요청 — 아직 코드·기존 회신으로 확정할 수 없는 항목

1. **전용 삭제 큐의 W2 수신 경계.** W1이 준비하는 전용 SQS queue/DLQ의 배포 환경별 식별값을 W2 설정에 어떤 비밀 관리 경로로 주입할지, W2 workload role에 필요한 `ReceiveMessage`/`DeleteMessage`/visibility 권한과 queue policy 소유자를 확인해 주세요. 실제 URL·ARN·계정번호·credential은 이 회신서에 적지 말고 승인된 보안 채널로 전달해 주세요. W1의 outer schema/message type은 기존 pin을 그대로 사용합니다.
2. **ACK callback 연결 설정.** W2에 제공할 HTTPS endpoint, 신뢰할 CA, bearer token의 비밀 주입·rotation 소유자, `X-EPICK-Service-Principal: w2` 검증의 배포 경계를 확인해 주세요. 실제 URL·인증값은 문서/로그/fixture에 남기지 않습니다. W1 endpoint의 private-only ingress가 W2 실행 위치에서만 접근 가능한지도 확인해 주세요.
3. **비정상 ACK 응답의 운영 처리.** W1 pinned callback 코드는 binding/도메인 오류를 `409 W2_DELETION_V2_BINDING_INVALID`, DB 오류를 `503 INTERNAL_RETRYABLE`로 반환합니다. 이 코드 의미는 재질의하지 않습니다. 다만 409가 반복될 때 W1/W2가 어떤 DLQ·수동 조사·재발행 절차를 사용할지와 담당자를 알려 주세요. W2는 `ACKNOWLEDGED`가 아닌 응답에서 SQS 메시지를 삭제하거나 성공으로 기록하지 않습니다. 503/timeout도 동일하게 실패 보존합니다.
4. **health/inspect 기대 인터페이스.** W1이 T050에서 요구하는 health와 inspect가 W2 CLI의 count-only 검사 및 프로세스/queue readiness로 충분한지, 아니면 특정 인증된 HTTP endpoint·응답 schema가 필요한지 명시해 주세요. 현재 W2에는 `commit_gate_operator inspect-run`이 있고 general source runtime에는 순수 `readiness()`/`health()` helper만 있습니다. 미합의 HTTP endpoint를 임의로 공개하지 않습니다.

W2는 이미 존재하는 bounded collection/gate/relay loop를 유지하고, 삭제 v2는 별도 bounded consumer CLI로 연결했습니다. CLI는 `preflight|consume-once|run`을 지원하며 `EPICK_DATABASE_URL`, `W2_PRIVATE_DELETION_REGION`, `W1_PRIVATE_DELETION_COMMAND_QUEUE_URL`, `W1_PRIVATE_DELETION_ACK_ENDPOINT`, `W1_PRIVATE_DELETION_ACK_BEARER`, `W1_PRIVATE_DELETION_ACK_CA_FILE`, `W1_EXPECTED_SYSTEM_SENDER_ID`를 요구합니다. 값은 이 문서에 적지 않습니다. 수신 visibility는 현재 60초 고정이며 자동 연장이 없으므로 W1과 공동 실행에서 실제 처리시간·재전달을 확인해야 합니다.

RenderedCollector는 별도 T050 gate이며, 승인된 개별 JS 공고·권리/robots·정적/API 부족 PoC가 확보될 때까지 구현·완료를 주장하지 않습니다. 한화인 후보는 2026-09-27 사용자가 `User-agent: *`와 `Disallow: /`를 제공하고 사이트 운영자의 예외 허가가 없음을 확인했으므로 수집 금지로 취급합니다. 이 사이트의 정적/API·브라우저 PoC는 실행하지 않습니다. 앞선 제한적 `robots.txt` HTTP 확인에서는 규칙 대신 HTML이 반환되어 독립적인 허용 판정도 얻지 못했습니다. 이 입력 요청은 W1에게 AWS 자원을 즉시 생성하거나 비밀을 평문 회신하라는 뜻이 아닙니다.
