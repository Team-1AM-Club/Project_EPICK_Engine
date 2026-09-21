# W2 → W3 C-01 연동 인계 (2026-09-21)

## 고정 기준과 상태

- W2 Engine `feat/crawler` 코드 full SHA: `40ca63447287432d5a127f6001fc984dc8980dd5` (앞선 이벤트 전달 커밋 `8a47f760e157fffabba58caf63a6fe4c361d8766` 포함).
- W3 Service 구현 full SHA: `35933e8037dc899f646b7b9af36909ae0e4b8f34` (W3 제공 기준).
- 계약: W1 transport envelope `1.0`, W2 payload `w2.source.v1`, W3 C-01 `0.2-candidate/r2`.
- **W2 코드·로컬 PostgreSQL 검증 완료. 실제 W2 producer → W3 process 및 W3 → W2 authority 조회의 공동 E2E·배포는 미완료.** 이 문서는 이를 완료된 것으로 승인하지 않습니다.

## W2가 제공하는 경로

1. `source_collection/w3_public_transport.py`의 `source_event_to_w3_wire`는 내부 `SourceEvent`를 W1 공통 envelope으로 변환합니다. outer `revision`은 해당 Source의 모든 공용 이벤트에 대한 연속 `aggregate_revision`이며, restriction 최신성은 payload의 별도 `restriction_revision`으로 판정합니다. `producer=w2`, `aggregate_type=source`, outer `schema_version=1.0`, payload `schema_version=w2.source.v1`을 명시합니다.
2. `record_source_restriction`은 새 제한 revision과 `source.restriction.changed` outbox 이벤트를 동일 PostgreSQL transaction에 저장합니다. 정확한 replay는 이벤트를 중복 생성하지 않습니다. outbox worker는 version·observation·restriction을 모두 전달할 수 있습니다.
3. `source_collection/w3_outbox_operator.py`는 W2 DB의 확정된 공용 outbox를 W3 `POST /c01/v1/events`로 보내는 일회성 실행 진입점입니다. W3 HTTP 200 JSON의 `receipt=COMMITTED` 및 동일 `event_id`를 확인해야 전달 완료로 기록합니다. 응답의 index ACK와 혼동하지 않습니다. 실패는 미전달 상태로 남겨 재시도·replay가 가능합니다. 원격 전송은 HTTPS만, 평문 HTTP는 loopback만 허용합니다.
4. `source_collection/source_authority_operator.py:create_app`은 W3 전용 `GET /internal/v1/sources/{source_id}/authority`를 W2의 `sources` PK에 연결하는 ASGI factory입니다. 요청은 주입된 Bearer token으로 인증합니다. 등록된 ID는 `{"source_id":"<canonical UUID>","registered":true}`, 미등록 ID는 `false`; DB/세션 장애는 `503 SOURCE_AUTHORITY_UNAVAILABLE`이며 `false`로 낮추지 않습니다. 공개 owner-scoped Source API나 Source metadata는 사용하지 않습니다.

## W1 배포 입력과 W3 연결

W1은 W2 DB의 `EPICK_DATABASE_URL`, W3 event endpoint의 `EPICK_W3_EVENT_ENDPOINT`, W3이 인정하는 W2 전용 `EPICK_W3_W2_TOKEN`, W2 authority 조회용 별도 `EPICK_W2_SOURCE_AUTHORITY_TOKEN`을 비밀 설정으로 주입해야 합니다. 사설 CA가 필요한 경우에만 `EPICK_W3_CA_FILE`을 지정합니다. 값 자체는 문서·로그·응답에 넣지 않습니다.

W1은 outbox operator의 주기 실행·재시도 감시와 SourceAuthority ASGI의 프로세스, 접근 제어, TLS/프록시, 네트워크 경로를 제공합니다. W3 C-01의 기본 loopback bind에 원격 W2가 직접 붙을 수 없으므로 W1의 내부 프록시/배치 결정이 필요합니다. W2의 일회성 실행 명령은 `python -m epick_engine.source_collection.w3_outbox_operator --limit 25`이고, 특정 이벤트 재전송은 `--replay-event-id <UUID>`입니다. Authority ASGI factory는 `python -m uvicorn epick_engine.source_collection.source_authority_operator:create_app --factory`로 실행 가능하지만 bind 주소·포트는 W1이 네트워크 설계에 따라 지정해야 합니다.

W3은 `SourceAuthority.is_registered(UUID)` 포트에 이 내부 GET의 인증된 client를 연결하고, 정확히 `registered=true`일 때만 등록으로 취급해야 합니다. `false`와 `503`/timeout은 서로 다른 결과로 처리해야 합니다. W3은 위 W2 full SHA로 기존 `scripts/verify_w2_w3_pin.py`를 재실행하고, W3 SHA와 함께 결과를 고정해 주십시오.

## 검증 증거와 남은 공동 Gate

- PostgreSQL 집중 테스트: `111 passed, 2 deselected` (`-k 'not migration'`); authority factory/API 별도 `10 passed`.
- 기존 실패 범주(오래된 migration head 기대값, 미구현 `PrivateDeletionCommand`·`RenderedCollector`)를 제외한 넓은 회귀 검사: `1665 passed, 43 deselected`. 전체 suite는 녹색이 아니며 이 결함들을 이번 연동의 완료 증거로 숨기지 않습니다.
- Ruff 전체 check, 변경 파일 format check, mypy `src`, `git diff --check`: 통과. W1 envelope·W2 payload·W3 C-01 schema에 대한 현지 synthetic version/observation/restriction fixture 9개 조합 검증: 통과.
- **미완료 공동 Gate:** W1 배포 설정 및 실제 endpoint 도달성, W3의 SourceAuthority client 결속, 네 이벤트 종류의 실제 송수신, duplicate/gap/conflict/replay/snapshot recovery, restriction `CLEARED` 이후 재색인, receipt와 index ACK의 분리 검증. W1·W3 담당자는 이 결과와 실행 환경·사용한 양쪽 full SHA를 회신해야 합니다.
