# W2 → W1: T050 삭제 v2 로컬 구현 인계 (부분 완료)

기준 W2 코드 commit: `76ae299101c7b2b8cb1b0d21a02ffe077a2f8ab5` (`feat/crawler`). W1 연동 기준은 Service `8d80a6f0edddd350a1e0308751fdb19bf7318d76`의 v2 dispatcher 및 인증된 단일 ACK callback입니다. 이 문서는 코드·로컬 검증 결과를 전달하며 T050/T058 완료 또는 운영 배포 승인을 뜻하지 않습니다.

## 이번에 연결한 경계

- `private_deletion_v2.py`: owner별 DB 잠금, 삭제 receipt·digest, DB commit 후 W1에 단일 v2 ACK. `STALE`은 callback하지 않고, exact replay는 `DUPLICATE` ACK로 재시도합니다.
- `w1_private_deletion_ack_client.py`: 검증된 HTTPS/CA, bounded timeout, bearer와 service principal. HTTP 200의 정확한 `ACKNOWLEDGED`만 성공으로 처리합니다.
- `private_deletion_consumer_v2.py`: W1 outer/inner v2 binding, canonical ID·UTC `Z`, SQS `SenderId` 검증. 성공 ACK 이후에만 메시지를 삭제하며 거부·실패·`STALE`은 삭제하지 않습니다.
- `private_deletion_operator_v2.py`: `python -m epick_engine.source_collection.private_deletion_operator_v2 preflight|consume-once|run`. DB head `0012_private_ack_wire_digest`, workload role, 전용 SQS queue/DLQ·암호화 metadata, ACK CA를 사전 확인합니다. 한 번에 한 건, 10초 long poll, 60초 visibility로 수신하고 종료 신호 뒤 현재 건을 마칩니다. 상용 AWS partition 외 region은 설정 단계에서 거부합니다.

## 재현 가능한 로컬 검증

- PostgreSQL 승인된 격리 테스트 DB에서 삭제 관련 integration/unit 111개 통과(비상용 partition 거부 변경 전); 변경 후 operator/consumer/ACK 집중 테스트 78개 통과.
- 변경 후 전체 `pytest -q --tb=no`: **2,156 passed, 8 failed, 1 skipped, 4 warnings**. 실패 8개는 모두 미구현 `RenderedCollector`를 요구하는 `test_rendering_safety.py`입니다. 승인된 JS-only 공식 개별 공고 및 정적/API 부족 PoC가 없어 T050 렌더링 gate를 통과하지 못했습니다. skip 1개는 실제 브라우저 검증 미실행입니다.
- Ruff check/format 통과, `mypy src` 39 source files 통과, Alembic head `0012_private_ack_wire_digest` 확인. 실제 AWS SQS, W1 private endpoint, 배포 DB에서의 end-to-end 결과는 아직 없습니다.

변경하지 않은 계약 파일 SHA-256:

| 파일 | SHA-256 |
| --- | --- |
| `contracts/w2-private/private-deletion-command-v2.schema.json` | `73eb3a51d15923969d483b13fdbf498e0a6cd8cfa18c019a66f5f532cfd64067` |
| `contracts/w2-private/private-deletion-ack-v2.schema.json` | `22cd9cd44061b5c14c9852634417482993a8ffb8f69dc8e98e3b6cd71b891bc9` |

## W1과 공동 실행 전 필요한 것

운영값·담당자 결정은 [삭제 runtime 입력 요청](w2-w1-t050-deletion-runtime-inputs-2026-09-27.md)에 분리했습니다. 실제 값은 승인된 비밀 채널로만 전달해 주세요. W1 전용 queue와 W2 IAM 권한, private ACK ingress·CA·secret, 409 DLQ 절차, health/inspect 기대 인터페이스를 확정한 뒤 W1/W2 공동 테스트에서 `APPLIED`·`DUPLICATE`·`STALE`·409·503/timeout·queue redelivery를 검증해야 합니다. 처리시간이 60초를 초과하면 visibility 만료로 중복 delivery와 DLQ 진입 가능성이 있으므로 실제 지연과 redrive도 확인해야 합니다.

한화인에는 사용자가 제공한 `User-agent: * / Disallow: /`와 사이트 운영자의 예외 허가 부재로 요청하지 않습니다. 다른 승인된 JS-only 공고가 없으므로 렌더링 실사이트 검증 및 T050/T058 최종 완료는 보류합니다.
