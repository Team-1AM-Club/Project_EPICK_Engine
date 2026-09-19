# W3 추가 회신 요청 — 후보 Restriction 계약의 채택 판단 자료

## 목적

제출한 `w3-restriction/0.1-draft`는 상세하고 일관된 local integration candidate입니다. 다만 W1의 D-05/D-06/D-07 계약으로 채택되지는 않았으므로, 재구현 요청이 아닌 팀 합의용 판단 자료를 요청합니다.

## 요청 사항

1. 팀이 채택할 경우 정본으로 삼을 schema·fixture·runbook의 경로와 version을 확정해 주십시오.
2. 아래 항목이 반드시 채택되어야 하는 규칙인지, 변경 가능한 후보인지 구분해 주십시오.
   - `source.restriction.changed`, event ID와 payload 불변 dedup
   - Source-wide `aggregate_revision`
   - `RESTRICTED`/`RELEASED`, accuracy/reason code enum
   - stale·conflict·gap·replay·snapshot의 fail-closed 처리
   - 전체 `IndexKey` readback 뒤의 ACK, `history_complete`, `generation`
3. W1 개인 삭제와 Source-wide restriction의 상호 작용을 명시해 주십시오.
   - 개인 삭제는 public restriction event가 아닌 W1 private lifecycle로 유지되는지
   - W3 replay/snapshot 또는 늦은 event가 삭제된 개인 데이터·표시 상태를 되살리지 않도록 W1/W3가 교환해야 할 최소 신호
4. W4에 전달하는 usability signal의 정본 DTO와, 기존 W4 앱이 지켜야 할 cache invalidation·generation 검증 조건을 제시해 주십시오.
5. W2 outbox가 실제로 연결될 때 필요한 producer 조건과 consumer response의 성공/실패 의미를 한 표로 정리해 주십시오.

## 회신 형식

| 항목 | 현재 draft 규칙 | 채택 필수 여부 | 변경 가능 범위 | 영향 받는 W1/W2/W4 계약 |
|---|---|---|---|---|

추가 구현이나 외부 배포는 요청하지 않습니다. 불일치가 있다면 schema를 수정하기 전에 먼저 계약 변경안을 제시해 주십시오.

## 완료 기준

W1·W2·W4가 후보 계약의 채택 범위와 공개/개인 경계를 같은 fixture로 검증할 수 있어야 합니다.
