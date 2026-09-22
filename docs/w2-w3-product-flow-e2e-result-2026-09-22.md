# W2 수집 runtime → W3 전달 로컬 E2E 결과 (2026-09-22)

판정: **합성 정적 채용공고 응답 → 실제 W2 runtime·파서·PostgreSQL 영속화/outbox → 고정 W3 C-01 HTTP 전달 통과**. W1 실서비스 조회·FINALIZE, 외부 공식 Source의 네트워크 fetch, W3 색인 및 운영 배포 완료 판정은 아니다.

## 고정 대상과 재현 경계

- W2 제품 코드 SHA: `7523d757d59ed0e28c9102ebf456140e76e2c493` (`src`, `migrations` 검증). W3 분리 checkout SHA: `0c4f01f9537a3129c976fae5e63111a7982c5da6`.
- `scripts/verify_w2_w3_postgres_http.py`를 `EPICK_TEST_DATABASE_APPROVED=1`, 승인된 loopback `EPICK_TEST_DATABASE_URL`로 실행했다. 실행별 임시 PostgreSQL schema·W3 SQLite DB·로컬 HTTP 프로세스를 사용하고 종료 시 정리했다.
- 외부 수집 I/O에는 `tests/fixtures/synthetic_sources/static_posting.html`을 반환하는 테스트 collector를 사용했다. W1 명령 조회도 테스트 응답이다. 이 두 경계를 제외한 `handle_collection_dispatch`, `SqlAlchemyCollectionInputProvider`, 정적 공고 파서, W2 DB·outbox, SourceAuthority, W3 publisher·HTTP 수락은 제품 구현이다. outbox 행을 검증 코드가 직접 삽입하지 않았다.

## 확인한 결과

| 경계 | 결과 |
| --- | --- |
| W2 수집·저장 | fixture fetch 1회, SourceVersion 1건, Evidence 15건, `source.version.available` 공용 outbox 1건(revision 1)을 생성했다. 채용공고의 `AWS experience is required.` 근거 발췌가 저장되었다. |
| W1 분리 경계 | 수집 attempt는 `PERSISTED`이며 W1 FINALIZE를 수행하지 않아 최신 Source 포인터는 비어 있다. 이를 수집/전달 성공과 혼동하지 않았다. |
| SourceAuthority·W3 | W2 Authority가 Source 등록을 확인했다. W3 status의 `event_cursor`는 0→1, 전달 후 `required_event_cursor`는 1이었고 index ACK는 false를 유지했다. W2 outbox delivery state는 `delivered`다. |
| 기존 복구 검증 | 같은 스크립트의 별도 합성 이벤트 10건, replay·snapshot·제한·미등록·Authority 장애 검증도 유지했다. 실행 전체 outbox delivery는 11건이다. |

최종 스크립트 실행은 exit 0, `status=PASS`, `product_collection_evidence_count=15`, `product_collection_outbox_delivered=true`, `product_collection_w3_cursor=1`이었다. 결과에는 DB URL, bearer token, Source 원문 또는 raw HTTP body를 기록하지 않았다.

## 검증과 남은 Gate

- 관련 PostgreSQL 통합 테스트 3개 파일: **57 passed**. `ruff check .` 및 변경 스크립트 `ruff format --check`: 통과.
- 전체 W2 pytest: **1781 passed, 14 failed, 1 skipped, 4 warnings**. 실패는 기존 `test_private_deletion.py` 6건, `test_rendering_safety.py` 8건에 한정된다. 전체 suite green이라고 보고하지 않는다.
- 변경 스크립트에 대한 단독 mypy 검사는 **29 errors**로 실패했다. 새 수집 helper 범위에는 오류가 없고 나머지 기존 스크립트 구간에 오류가 남아 있다. 이 검사를 통과한 것으로 보고하지 않는다.
- 실제 외부 공식 Source 네트워크 fetch, W1 명령·FINALIZE와 최신 포인터 승격, W3 색인 ACK, 운영 SQS/IAM·모니터링, G-07 보존·pruning/`F>0` 및 T067–T069 전체 완료는 별도 Gate다.

재현 명령과 복구 주의사항은 [W2 → W3 운영 인계](w2-w3-recovery-operator.md)를 따른다.
