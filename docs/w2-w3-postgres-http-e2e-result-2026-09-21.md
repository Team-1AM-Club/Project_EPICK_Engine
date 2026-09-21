# W2–W3 로컬 PostgreSQL/HTTP 공동 검증 결과 (2026-09-21)

W3의 이전 합성 세션 검증을 실제 W2 PostgreSQL outbox와 W2/W3 각각의 HTTP 프로세스로 확장했다. 결과 JSON은 [w2-w3-postgres-http-e2e-result-2026-09-21.json](w2-w3-postgres-http-e2e-result-2026-09-21.json)이다.

## 고정 구현과 실행 범위

- W2 Source Collection 코드·migration: `40ca63447287432d5a127f6001fc984dc8980dd5`. 실행 checkout의 `src/`, `migrations/`가 이 SHA와 동일함을 검증했다. 실행 시 checkout HEAD는 문서 commit `7876b824da368b78e28ce9ddf049694c1112f5ad`였다.
- W3 C-01: `0c4f01f9537a3129c976fae5e63111a7982c5da6`의 격리 checkout과 `uv.lock` 환경. W3 `src/`는 미수정 상태였다.
- W3가 제공한 공개 이벤트 fixture 4건(`version-available`, `version-partial`, `observation-changed`, `restriction-changed`)을 W2의 고유한 임시 PostgreSQL schema에 `OutboxEvent`로 적재했다. 해당 Source/Company도 합성 데이터로 등록했다. 이후 합성 `restriction CLEARED` 1건과 순서 역전 `observation` 2건을 추가했다. 별도 합성 Source에는 재배포 허용 정책을 명시해 버전·제한 활성화·해제 이벤트 3건과 index ACK/검색 차단·복구를 검증했다.
- W2 Alembic `upgrade head`를 임시 schema에 적용했다. 실제 W2 Authority ASGI 프로세스와 W3 C-01 HTTP 프로세스를 loopback으로 연결했다. 세 토큰과 Authority 토큰은 실행 중에 생성하고 출력·저장하지 않았다.
- 임시 schema와 W3 SQLite 파일은 실행 종료 후 정리했다. `--max-ttl-seconds 300`은 **로컬 검증 전용 값**이며 운영 TTL 승인으로 취급하지 않는다.

## 확인한 결과

| 검증 | 결과 |
|---|---|
| Authority 중단 중 W2 outbox worker 전달 | 실패를 반환하고 초기 4건 모두 `pending` 유지 |
| 등록 Source / 미등록 Source Authority 조회 | 각각 `registered=true` / `false` |
| Authority 복구 후 W2 outbox → W3 HTTP | 초기 4건 모두 전달·정확한 receipt 확인 후 `delivered` |
| 초기 W3 적용 상태 | `event_cursor=4`, `restriction_revision=1` |
| 기존 event replay | 성공; cursor 증가 없음, outbox 상태 유지 |
| W3 프로세스 재시작 | SQLite에서 동일 cursor·제한 revision 복원 |
| 미등록 대체 Source를 참조하는 제한 해제 | W3 거부, W2 outbox `pending`, cursor 4 유지 |
| 대체 Source 등록 후 재전달 | 제한 해제 수용; `restriction_revision=2`, cursor 5 |
| revision 7 선전달 후 revision 6 전달 | cursor 5에서 `EVENT_GAP`·요구 cursor 7을 기록한 뒤 cursor 7로 복구 |
| 기존 Source의 W3 index ACK | 최종 `false`, `OBSERVATION_BLOCKED`; 전달 receipt를 index ACK로 오인하지 않음 |
| 재배포 허용 합성 Source의 W3 index ACK | 최초 인덱싱 후 `true`; 제한 활성화 즉시 `false`·검색 제외; 제한 해제만으로는 `false`, 재인덱싱 후 `true`·검색 복구 |

검증 스크립트: [scripts/verify_w2_w3_postgres_http.py](../scripts/verify_w2_w3_postgres_http.py). `EPICK_TEST_DATABASE_APPROVED=1`과 격리된 로컬 `EPICK_TEST_DATABASE_URL`을 설정한 후 아래처럼 실행한다.

```powershell
.venv\Scripts\python.exe scripts\verify_w2_w3_postgres_http.py `
  --w3-checkout <W3 고정 checkout> `
  --w3-sha 0c4f01f9537a3129c976fae5e63111a7982c5da6 `
  --w2-code-sha 40ca63447287432d5a127f6001fc984dc8980dd5
```

추가 검증: W2 Authority·transport·outbox 테스트 `31 passed`, atomic persistence·restriction mutation 테스트 `64 passed`; W3 고정 환경 전체 테스트 `288 passed, 1 skipped`(live provider 설정 필요). 낡은 migration head 기대값 4건을 현재 `0008_collection_runtime` 계보로 갱신했다. 검증 스크립트 Ruff check·format check 통과.

W2 전체 회귀는 `1693 passed, 14 failed, 1 skipped, 4 warnings`다. 남은 실패 6건은 현재 W2 `worker.py`에 없는 `PrivateDeletionCommand` import, 8건은 현재 `collector.py`에 없는 `RenderedCollector` 참조에서 발생한다. 이 두 미구현 영역의 테스트를 연동 통과로 포장하지 않았고, 이번 W2–W3 이벤트 경계 검증과 분리해 남겨 둔다. skip 1건은 T048 실제 브라우저 검증에 필요한 승인된 Playwright·브라우저·외부 접속 조건이 없기 때문이다.

## 아직 검증하지 않은 경계

- 이 검증은 **합성 fixture를 outbox에 적재한 경로**다. 실제 채용공고 수집·SourceVersion/Evidence 영속화부터 W3 인덱싱까지의 전체 제품 E2E라고 주장하지 않는다.
- 원래 W3 fixture Source의 ACK는 관측 제약 아래 `OBSERVATION_BLOCKED`다. 별도 재배포 허용 합성 Source의 W3 index ACK와 검색 차단·재인덱싱은 검증했지만, 실제 Source 정책 승인이나 W4 조회까지 검증한 것은 아니다.
- W1 배포 환경의 IAM/SQS, TLS, registry, 스케줄링, 장애 복구와 W1/W4 공동 테스트는 범위 밖이다.

W3에는 이 결과와 두 구현 SHA를 전달해 기존 `postgres_outbox_e2e=NOT_RUN` 항목을 본 로컬 범위의 `PASS`로 갱신할 수 있는지 확인한다. W1에는 이후 W3 실행·배포 경계와 남은 index ACK/공동 테스트를 분리해 전달한다.
