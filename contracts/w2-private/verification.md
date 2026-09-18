# W2 private commit-gate 검증 기록

작성일: 2026-09-18. 대상은 Engine `feat/crawler`의 W2 독립 산출물이다. 이 문서의 수치는 해당 작업공간에서 직접 실행한 결과이며 실제 W1/W2 queue 왕복 또는 공동 CT15 결과가 아니다.

## 기준과 재현

- W1 Service 계약 검토 pin: `afec08a9602132e5e433b523b0b6804850440524`.
- W2 후보: `W2_UNADOPTED_PROPOSAL_QUEUE_DISCONNECTED`.
- PostgreSQL 통합 검사는 승인된 loopback test DB에서 수행했다. `EPICK_TEST_DATABASE_APPROVED=1`과 `EPICK_TEST_DATABASE_URL`을 실행 프로세스에만 제공한다. 실제 DSN·credential은 Git에 저장하지 않는다.
- 테스트는 UUID별 격리 schema를 생성·정리한다. Migration 검사는 해당 schema에서 Alembic `0003_source_retention_origin` → `0004_private_commit_gate` upgrade와 metadata 일치를 확인했다. 운영 DB에는 적용하지 않았다.

Engine 루트에서 실행한 명령과 결과:

| 명령 (`.venv/Scripts/python.exe` 뒤 인수) | 결과 |
| --- | --- |
| `-m pytest tests/unit tests/contract -q --tb=short` | 1006 passed, skip 0 |
| `-m pytest tests/integration/source_collection/test_private_commit_gate.py tests/integration/source_collection/test_private_deletion.py tests/integration/source_collection/test_recovery_faults.py -q --tb=short` | 47 passed, 기존 T067 6 failed |
| `-m pytest tests/integration/source_collection/test_foundation_storage.py tests/integration/source_collection/test_atomic_persistence.py -q --tb=short` | 36 passed |
| `-m ruff check src tests migrations` | All checks passed |
| `-m ruff format --check src tests migrations` | 65 files already formatted |
| `-m mypy` | 13 source files, no issues |

T082 transport focused 296 passed, T083 gate·transport·runtime focused 418 passed, T084 private PostgreSQL 35개 테스트를 포함한다. 신규 동작은 RED→GREEN으로 검증했고 작업별 독립 리뷰와 최종 전체 리뷰에서 actionable finding이 남지 않았다. JSONB에 허용되지 않는 합성 문자열 및 DB statement 오류의 private 내용 노출을 회귀 테스트로 막고, 실패 후 caller transaction 재사용을 확인했다.

기존 T067 실패 6건은 `worker.PrivateDeletionCommand` / `process_private_deletion` 미구현으로 인한 사전 작성 EXPECTED RED다. 계정·Project 전체 삭제 완료 근거로 이 산출물을 사용하지 않는다. W1 raw ACK adapter, lease 확보, digest 채택, parser/routing, concrete result/checkpoint callback, 실제 queue 및 공동 CT15도 미완료다. QUESTION_MATCHING의 company pin null/command UUID 결속 충돌은 pinned W1 계약·runtime에서 확인되어 W1 수정 전까지 fail-closed다.

[인계서](W2_Implementation_Handoff_2026-09-18.md)에는 W1 결정 요청, [artifact manifest](artifacts.sha256)에는 이 저장소에서 접근할 파일별 SHA-256을 기록한다. 파일별 checksum은 Git commit SHA가 아니다.
