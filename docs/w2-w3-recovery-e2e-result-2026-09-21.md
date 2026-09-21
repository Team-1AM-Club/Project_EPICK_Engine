# W2 → W3 replay·snapshot 로컬 공동 E2E 결과 (2026-09-21)

판정: **합성 격리 PostgreSQL outbox → 고정 W3 C-01 HTTP 복구 Gate 통과**. 실제 Source 수집·운영 배포·T067–T069 전체 완료 판정은 아니다. 기계 판독 결과는 [JSON](w2-w3-recovery-e2e-result-2026-09-21.json)에 있다.

## 고정 대상과 실행 경계

- W2 제품 코드: `c27e6f318080b2a382aa93833bf3de3d87a1cb2a`; W3: `0c4f01f9537a3129c976fae5e63111a7982c5da6`.
- W3는 위 SHA의 분리 checkout, W2는 승인된 loopback PostgreSQL 테스트 DB 안의 실행별 임시 schema와 Alembic upgrade, W3는 실행별 임시 SQLite DB를 사용했다. 입력은 W3의 공개 합성 fixture 및 추가 합성 event다. 검증 종료 시 임시 schema·DB·프로세스를 정리했다.
- `scripts/verify_w2_w3_postgres_http.py`를 위 두 SHA와 `EPICK_TEST_DATABASE_APPROVED=1`, 승인된 `EPICK_TEST_DATABASE_URL`로 실행해 exit 0 및 `status=PASS`를 받았다. 결과 파일에는 DB URL, bearer token, Source 원문, raw HTTP response body를 넣지 않았다.

## 확인한 복구 동작

| Gate | 실제 확인 결과 |
| --- | --- |
| replay | 별도 W3 DB에서 revision 7만 먼저 받아 `event_cursor=0`, `required_event_cursor=7`, `EVENT_GAP`을 확인했다. W2 복구 operator 실행 후 `event_cursor=7`, `restriction_revision=2`; W2 outbox delivery state는 전후 동일했다. |
| 명시적 snapshot | 또 다른 W3 DB에서 `H=3`, `R=2` snapshot 적용. 직후 `history_complete=false`, `index_ack=false`; W3 operator index endpoint에서 재색인한 뒤에만 `index_ack=true`. W2 outbox delivery state는 동일했다. |
| 불변 충돌 | 이미 수락된 W3 event와 동일 identity/revision의 다른 fact를 주입해 W3 `CONFLICT`를 확인했다. 재실행한 W2 replay는 `W3_RECOVERY_FAILED`로 실패 종료하고 W2 outbox를 변경하지 않았다. |
| Source 미등록 | W2에 없는 Source ID는 복구 성공으로 표시되지 않았고 W3 cursor도 0에 머물렀다. |
| SourceAuthority 장애 | Authority 연결이 불가능한 별도 W3 DB에서 replay가 실패 종료했고 cursor 0 및 index ACK false를 유지했다. |

기존 공개 outbox 전달 검증도 같은 실행에서 보존했다: Authority 장애 시 pending 유지, 10건 delivery, restriction/해제와 EVENT_GAP 복구, 재시작 상태 보존, 제한 후 검색 차단 및 재색인 ACK를 확인했다. 이는 복구 신규 Gate와 별도의 기존 synthetic 검증이다.

## 코드 검증과 남은 Gate

- 신규 복구 관련 unit 4개 파일: **95 passed**. PostgreSQL 통합 2개 파일(`test_w3_recovery_store.py`, `test_source_outbox.py`): **21 passed**. Ruff check 통과.
- 전체 W2 pytest는 **1780 passed, 14 failed, 1 skipped, 4 warnings**였다. 실패 14건은 기존 `test_private_deletion.py` 6건과 `test_rendering_safety.py` 8건이며 신규 복구 테스트 실패는 없었다. 전체 suite green으로 표시하지 않는다.
- 실제 채용공고 Source 수집 → W2 영속화/outbox → W3 전달은 이번 합성 Gate에 포함되지 않는다. G-07 보존기간·pruning·`F>0`, W1 배포/IAM/SQS/운영 자격증명·모니터링, T067–T069 전체 완료도 보류다.

재실행·실패 처리 방법은 [복구 operator 인계](w2-w3-recovery-operator.md)를 따른다. W3 담당자의 회신은 프로젝트 `.agents/docs/reply_260921/w2-w3-local-e2e-contract-response-2026-09-21-v2.md`이며, W3 SHA 및 미완료 Gate 판정은 변경하지 않았다.
