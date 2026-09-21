# W2–W3 replay·snapshot producer 설계 (2026-09-21)

상태: **2026-09-21 사용자 승인 설계**. 이 문서는 제품 코드 구현·운영 보존기간 승인·W2–W3 전체 연동 완료를 뜻하지 않는다.

## 목적과 승인된 범위

W2의 이미 보존된 공용 Source outbox를 정본으로 사용해, W3 C-01이 누락 이벤트를 `Replay` batch로 받고 필요할 때 원자 `Snapshot`으로 다시 시작할 수 있게 한다. 사용자는 2026-09-21에 **보존된 이력 기반 replay·snapshot producer를 진행하되 운영 보존기간은 미정으로 남기는 범위**를 승인했다. W1 배포·IAM/SQS, W4 소비, 실제 채용공고 수집과 운영 삭제/보존 정책은 이 설계의 완료 조건이 아니다.

현재 W2 `OutboxEvent`는 Source별 `(aggregate_id, aggregate_revision)` 유일성과 불변 event ID/payload를 갖고, `worker._source_event_from_outbox_row`가 public `SourceEvent`로 재검증하며, `source_event_to_w3_wire`가 W1 envelope `1.0`으로 변환한다. `w3_outbox_operator`의 현 `--replay-event-id`는 단일 event 재발행일 뿐 W3 `/replay`·`/snapshot` producer가 아니다. W3 기준은 Service `0c4f01f9537a3129c976fae5e63111a7982c5da6`, `contracts/c01/v0.2-candidate/{replay,snapshot}.schema.json`, `docs/w3-additional-reply-2026-09-16.md` §5·§7이다. W2 기준은 Engine `40ca63447287432d5a127f6001fc984dc8980dd5`의 제품 코드와 `69f8984dba2f3c56d66c97f8a9edd5de5c4513ff`의 검증 결과다.

## 검토한 접근과 선택

1. **선택: 보존된 outbox에서 읽을 때 복구 표현을 구성한다.** 기존 불변 event와 wire 변환을 재사용하고 새 상태 테이블·migration 없이 로컬 안전성 검증을 할 수 있다. 이 단계에서 안전하게 선언할 수 있는 `retention_floor_cursor`는 `0`뿐이다. 이력 누락이 확인되면 snapshot까지 포함해 fail-closed한다.
2. 매 공용 event commit마다 별도 authoritative snapshot projection을 갱신한다. 향후 outbox pruning에는 유리하지만 모든 producer 경로와 migration·복구를 동시에 바꿔야 한다. G-07 보존기간이 아직 없으므로 이번 범위에는 넣지 않는다.
3. W3의 현재 SQLite 상태를 W2 snapshot으로 되돌려 보낸다. W3는 소비자이므로 원본 누락·충돌을 정본으로 교정할 수 없다. 채택하지 않는다.

## 데이터·트랜잭션 경계

- Source ID는 W2 `sources`에 등록된 UUID여야 한다. W2 복구 생성기는 한 Source만 대상으로 하며 W1 개인 Job/owner 정보나 비공개 staged result를 읽거나 내보내지 않는다.
- 한 생성 요청의 Source row, 해당 `OutboxEvent`와 high watermark `H`는 하나의 PostgreSQL read-only `REPEATABLE READ` snapshot에서 읽는다. W2 생산 transaction과 섞지 않는다. 먼저 Source 존재를 확인하고 `H=max(aggregate_revision)`을 계산한다. 공용 revision이 `1..H`로 연속이고 event ID·타입·payload·wire가 유효한지 확인한다. 직렬화할 내용을 메모리에 확정하고 읽기 transaction을 닫은 **뒤** W3 HTTP를 호출해 외부 요청 중 DB transaction을 오래 유지하지 않는다. 빈 Source는 복구 가능한 공용 상태가 아니므로 `complete=true` snapshot을 만들지 않는다.
- 이 단계에는 outbox pruning writer를 추가하지 않는다. 이력이 `1..H`로 완전할 때에만 `F=0`이라고 선언한다. 누락된 행을 발견해도 `F`를 추정하거나 빈 성공으로 바꾸지 않는다. 복구 불가 오류를 반환하고 W3 cursor/index 상태를 정상으로 표시하지 않는다. 향후 유한 보존을 도입할 때는 authoritative 최신 상태 projection과 정확한 F/H metadata를 별도 설계·migration·운영 승인(G-07)으로 추가해야 한다.
- `H`, `F`, `restriction_revision`은 역할이 다르다. `H`는 Source 전체 공용 event revision의 현재 최고값, `F`는 replay 가능한 경계(현재 0), `restriction_revision`은 제한 상태의 Source별 최고 연속 번호다. 서로 대체하지 않는다. 공용 event payload와 원본 시각·ID를 변경하지 않는다.

## Replay batch

- 입력은 W3가 durable하게 보고한 `source_id`, `after_cursor=A`다. W2는 `A`가 음수/비정수이거나 `A>H`이면 전송하지 않고 오류를 반환한다. 상태 조회 응답의 Source ID와 cursor를 정확히 검증하고, 호출자가 임의 cursor를 올려 누락을 건너뛰지 못하게 한다.
- 한 읽기 snapshot의 `H`를 `high_watermark`로 고정하고 `A<revision<=H` 중 오름차순으로 최대 500건을 선택한다. page가 500건을 넘으면 다음 page의 `after_cursor`는 W3가 확인한 durable cursor다. 각 event는 기존 `_source_event_from_outbox_row`와 `source_event_to_w3_wire`를 거친다. `schema_version="w3-c01/0.2-candidate"`, `source_id`, `after_cursor`, `high_watermark=H`, `retention_floor_cursor=0`, `events`를 W3 schema에 맞춘다.
- 이벤트 0건도 `A=H`인 정합한 batch일 때만 허용한다. `A<H`인데 선택된 행이 없거나 revision에 빈 구간이 있으면 전송하지 않는다. W3의 HTTP 200은 곧 복구 성공이 아니다. `outcome`, `event_cursor`, `required_event_cursor`, Source ID를 검사하며 `INCOMPLETE`는 다음 page가 필요한 상태, `REPLAYED`는 cursor가 H에 도달했을 때의 성공으로만 처리한다. `CONFLICT`, `CURSOR_AHEAD`, 예상치 못한 `SNAPSHOT_REQUIRED`, 인증/통신/Schema 오류는 fail-closed한다. 응답의 `index_ack`를 transport receipt로 해석하지 않는다.

## Atomic snapshot

- 같은 read snapshot에서 `1..H`의 모든 유효 공용 event를 재생성한다. `versions`는 `source_version_id`별 최신 `source.version.available` event, `restrictions`는 `restriction_id`별 최신 `source.restriction.changed` event(해제 상태 포함), `observation`은 Source의 최신 `source.observation.changed` event 하나 또는 `null`이다. 각 목록은 aggregate revision 오름차순으로 직렬화한다. W3 schema의 `versions`·`restrictions` 각 최대 500건을 넘으면 불완전 snapshot을 보내지 않고 복구 한계로 실패한다.
- `event_cursor=H`, `restriction_revision`은 Source 공용 이력 안의 최대 제한 순번(없으면 0), `complete=true`다. 제한 순번이 1부터 연속이고 aggregate revision·ID에 충돌이 없는지 검증한다. `as_of`는 read snapshot에서 확정한 시각과 포함 event의 최대 `occurred_at` 중 늦은 값으로 정해 W3의 시각 조건을 만족한다. 기존 event identity와 payload는 재작성하지 않는다.
- snapshot은 W3가 보고한 현재 cursor·required cursor·restriction watermark보다 낮으면 전송하지 않는다. 구성한 payload를 read transaction 종료 후 W3 `/snapshot`에 전송하고, `SNAPSHOT_APPLIED`와 정확한 Source/cursor/watermark를 검증한다. W3가 기존에 알고 있는 불변 사실과 충돌해 `CONFLICT`를 반환하면 자동으로 덮어쓰거나 W3 DB를 지우지 않는다. 승인된 운영자 조치가 필요하다. Snapshot 수락은 `history_complete=false`와 index 폐기를 수반하므로 index ACK가 다시 true가 되었다고 주장하지 않는다.

## 실행·보안 경계

- 기존 W2 W3 전용 bearer/HTTPS 또는 loopback HTTP 정책, TLS 검증, timeout, 응답 크기 상한, redirect·자동 retry 차단을 복구 POST/상태 GET에도 적용한다. 운영 endpoint와 token은 환경 설정으로만 주입한다. 원문·token·DB URL·응답 body를 로그·오류에 남기지 않는다.
- Source ID를 명시하는 별도 W2 복구 operator를 제공한다. 이 operator가 W3 status를 읽고 필요한 replay page 또는 명시적 snapshot을 발행한다. 새 공개 사용자 HTTP route, W3 DB 직접 접근, W1 Job 상태 변경, 자동 주기 스케줄러는 만들지 않는다. W1의 실제 배포 트리거·자격 증명·운영 관측은 후속 통합 Gate다.
- 전송 전 구성·DB 무결성 오류는 외부 POST 0회를 보장한다. W3에 일부 page가 반영된 뒤 전송이 실패하면 W2 원본은 변경하지 않는다. 동일 Source를 다시 실행할 때 W3 durable cursor부터 재개하고 event identity를 유지한다.

## 검증 기준과 미포함 범위

- 순수 producer 계약: Source 미등록, 전체 이력 없음, revision gap, 중복/변조, `A>H`, 0/1/500/501건 page, 제한 R gap, 해제 상태·복수 제한 ID·복수 Version, observation 유무, W3 schema 및 개인 필드 0건.
- 승인된 격리 PostgreSQL: 동시 event append 중 read snapshot 정합성, page 실패·재실행의 동일 event, rollback 후 H, 원본 outbox delivery state 불변.
- 고정 W3 HTTP 로컬 공동 실행: replay로 W3 gap cursor 복구, F/H 의미, 새 W3 DB 초기 snapshot, snapshot 후 index ACK false·재색인 후 true, conflict/미등록 Source/Authority 장애의 fail-closed. 합성 fixture와 실제 PostgreSQL outbox는 구분해서 기록한다.
- 실제 Source 수집부터 end-to-end, outbox pruning 및 F>0, 운영 보존기간, W1 SQS/IAM·배포, W3/W4 제품 사용, T067/T068/T069 전체 완료는 **별도 Gate**다. W2 전체 테스트의 기존 미구현 실패 14건을 신규 복구 코드의 성공으로 포장하지 않는다.

## 후속 구현 계획으로 넘길 파일 경계

W2 `source_collection` 안에 읽기/조립 책임을 분리하고 기존 `worker._source_event_from_outbox_row` 및 `w3_public_transport.source_event_to_w3_wire`를 재사용한다. 별도 복구 operator와 전용 unit·contract·PostgreSQL·W3 HTTP 통합 테스트를 둔다. 파일명·작업 순서·명령은 사용자 문서 승인 후 상세 구현 계획에서 확정한다. 기존 단일 event 발행과 private commit gate 경로는 변경하지 않는다.
