# W2 → W3 Source replay·snapshot 운영 인계

상태: 로컬 합성 PostgreSQL → 고정 W3 HTTP 공동 검증 완료. 운영 배포·실제 Source 수집 연동 완료를 뜻하지 않는다.

## 전제와 실행

- W2 PostgreSQL에 해당 Source가 등록되어 있고 공용 outbox revision `1..H`가 누락 없이 보존되어 있어야 한다. 현재 생산 가능한 replay floor는 **`F=0`만** 허용한다. 유한 보존기간·pruning 또는 누락 이력에서 `F>0`을 추정하지 않는다.
- W3 C-01 endpoint와 W2 전용 bearer는 운영자가 승인된 비밀관리 경로로 주입한다. 필수 환경 변수는 `EPICK_DATABASE_URL`, `EPICK_W3_EVENT_ENDPOINT`(정확히 `/c01/v1/events`로 끝나는 HTTPS URL 또는 로컬 loopback HTTP), `EPICK_W3_W2_TOKEN`이다. 사설 CA가 필요한 HTTPS에는 선택 변수 `EPICK_W3_CA_FILE`을 사용한다. 값이나 응답 원문을 명령 이력·문서·이슈에 복사하지 않는다.
- Source UUID를 확인한 뒤 아래 명령을 한 Source씩 실행한다. `--mode`를 생략하면 replay다. snapshot은 자동 대체되지 않으며 운영자가 명시적으로 선택해야 한다.

```powershell
python -m epick_engine.source_collection.w3_recovery_operator --source-id <registered-source-uuid> --mode replay
python -m epick_engine.source_collection.w3_recovery_operator --source-id <registered-source-uuid> --mode snapshot
```

`REPLAYED`는 W3 durable cursor가 읽기 snapshot의 `H`에 도달했다는 뜻이고, `ALREADY_CURRENT`는 W3가 이미 그 cursor에 있다는 뜻이다. `SNAPSHOT_APPLIED`는 원자 snapshot이 수락되었다는 뜻이다. 세 응답 모두 검색 index가 준비되었다는 의미가 아니다. 실패 출력은 `W3_RECOVERY_FAILED`로 제한되며, 원인을 확인하기 전 cursor를 임의로 올리거나 W3 DB를 삭제하지 않는다.

## 복구와 재시도 규칙

Replay는 W3가 보고한 durable cursor에서 시작하고 한 페이지 최대 500개 event를 보낸다. W2는 각 요청에서 공용 이력의 연속성·event identity·wire를 검증하고 읽기 transaction을 닫은 후 HTTP를 호출한다. W3가 일부 페이지를 commit한 뒤 timeout이 나도 W2 outbox delivery state는 바꾸지 않는다. 같은 replay 명령을 다시 실행하면 W3 status를 새로 읽고 그 cursor부터 이어간다. 응답이 `INCOMPLETE`이면 W3 status를 다시 확인한 뒤 다음 페이지로 진행한다. `CONFLICT`, cursor 역행·초과, 인증/통신/Schema 오류, 예상치 못한 `SNAPSHOT_REQUIRED`에서는 실패 종료한다.

전송 body 상한은 2,000,000 byte, 응답 상한은 65,536 byte다. 500개 이하라도 body 상한을 넘으면 임의 분할·생략하지 않고 실패한다. W3가 요구하는 `H`, `restriction_revision`, `F`는 서로 다른 값이며 운영자가 임의로 치환하지 않는다.

명시적 snapshot은 보존된 전체 `1..H` 이력에서 최신 Version·restriction·observation을 조립한다. W3의 현재/required cursor 또는 restriction watermark가 W2보다 높으면 전송하지 않는다. 적용 후 W3는 `history_complete=false`, `index_ack=false`로 시작하며 W3 운영자가 별도 index 작업을 마쳐야 검색 ACK가 true가 된다. snapshot은 기존 W3 index를 무효화할 수 있으므로 replay 실패의 자동 우회책으로 사용하지 않는다. W3의 불변 사실과 충돌하면 덮어쓰지 않고 W2/W3 담당자가 증거를 대조한다.

## 격리 로컬 재현

검증 스크립트는 승인된 loopback PostgreSQL 테스트 DB만 받으며 매 실행마다 UUID 이름의 schema를 만들고 Alembic upgrade 후 정리한다. W3는 고정 SHA `0c4f01f9537a3129c976fae5e63111a7982c5da6`의 별도 checkout과 임시 SQLite DB를 사용한다. 아래 두 테스트 변수의 **실제 값**은 로컬 테스트 환경에서만 별도로 설정한다. `EPICK_TEST_DATABASE_URL`을 운영 DB로 지정하지 않는다.

```powershell
$env:EPICK_TEST_DATABASE_APPROVED = '1'
# EPICK_TEST_DATABASE_URL: 승인된 격리 loopback PostgreSQL 테스트 DB로 별도 설정
python scripts/verify_w2_w3_postgres_http.py --w3-checkout <pinned-w3-checkout> --w3-sha 0c4f01f9537a3129c976fae5e63111a7982c5da6 --w2-code-sha c27e6f318080b2a382aa93833bf3de3d87a1cb2a
```

검증 결과는 [로컬 공동 E2E 결과](w2-w3-recovery-e2e-result-2026-09-21.md)에 기록한다. 합성 fixture와 실제 PostgreSQL outbox → HTTP 검증이며 실제 채용공고 수집부터의 경로는 검증하지 않았다.

## 미완료 Gate

- G-07: 보존기간·pruning·`F>0`과 authoritative 최신 상태 projection의 설계/운영 승인이 없다. 현재는 전체 공용 이력 보존 및 `F=0`만 성립한다.
- W1 배포·IAM/SQS·자격 증명 배포와 실제 실행 위치, W3/W4 제품 사용 및 공동 운영 모니터링은 별도 연동 Gate다.
- 실제 Source 수집 → 영속화/outbox → W3 전달의 제품 경로는 이 합성 검증 범위 밖이다.
- T067–T069 전체 완료 또는 W2–W3 운영 연동 완료로 표시하지 않는다. 앞선 전체 W2 테스트에는 신규 복구와 무관한 기존 실패 14건이 보고되었으며, 이 결과를 전체 suite green으로 해석하지 않는다.
