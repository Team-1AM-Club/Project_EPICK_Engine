# W4 → W1: R3-05 제출 초안 및 회사 결속 수정 요청

작성일: 2026-09-18. **외부 미발송 / 로컬 구현 미커밋 / 팀 채택 전 / 실제 queue 미연결**.

W2 인계서의 R3-05 중 W4 → W1 Core Decision 범위에 대해 아래 산출물을 준비했습니다. W3 C01 usability 전달이나 W4 추천 결과 저장을 Core Decision 수신 계약으로 대체하지 않았습니다. W2 staged-result/ACK 채택 항목은 W1/W2 소관으로 남습니다.

| R3-05 항목 | W4 제출 내용·상태 |
| --- | --- |
| schema | Service `afec08a9602132e5e433b523b0b6804850440524`의 envelope·payload·receipt 바이트를 그대로 사용 |
| 정상/음성 fixture | QUESTION_MATCHING Core/non-Core 각 1개, 거부 메시지 20개, receipt 6종, 회사 충돌 재현 3개+정상 대조군 1개 |
| producer 코드 | `prepare_decision`, `check_current`, `receipt_outcome`. 서버가 지정한 결정만 생성, 실제 전송·자동 판단 정책 없음 |
| input/owner | 서버 문맥의 owner/project/question/Source/입력 버전·권한 revision 검사. 문맥 조회 API와 authoritative DB 검사는 W1과 합의 필요 |
| stale/dedup | 변경·철회·새 버전·cursor 역행 차단, 같은 제출 ID/시각/본문 보존. W1 receipt의 중복/오래된 버전 처리와 구분. 영속 outbox 미구현 |
| pin | 기존 W1 계약 pin과 파일별 SHA-256 제공. 새 W4 완료 Git pin은 아직 없음. ZIP/manifest는 로컬 파일 전달본 |
| producer readiness / CT-12 | 로컬 codec/fixture 검증 완료. 실제 queue·재시작·동시성·공동 CT-12 미실행. 선행 조건은 계약 문서 마지막 절 |

자료: [계약과 실행법](w4-core-decision-contract-2026-09-18.md), [코드](../epick_w4/core_decision.py), [테스트](../tests/test_core_decision.py), [고정 파일 provenance](../epick_w4/core_decision_schemas/baseline.json).

검증 결과: **전체 381개 테스트 통과(추가 30개), 실패/오류/skip 0**, 가상 HTTP 시연 2개 통과. 실제 모델·W1/W2 네트워크 전송 0회. W2가 보고한 unit/PostgreSQL 결과를 재실행한 것은 아닙니다. 기존 모델 성능 보고서와 운영 모델 선정 보류 상태는 변경하지 않았습니다.

W2가 지적한 QUESTION_MATCHING의 회사 충돌은 지정 Service pin으로 직접 재현했습니다. pin company null + command company UUID는 W2 schema를 통과하지만 W1 runtime에서 거부됩니다. command도 null로 바꾸면 runtime은 통과하지만 W2 schema에서 거부됩니다. pin까지 UUID로 바꾸면 QUESTION_MATCHING 범위 검사를 통과하지 못합니다.

**W1 회신 요청:** 아래 항목별로 `채택 / 수정 필요 / 미결정`과 적용 파일·접근 가능한 full SHA·담당자·다음 제공 조건을 알려 주세요.

1. **회사 결속:** QUESTION_MATCHING의 company null은 유지하고, 수집 company는 인증된 owner/project/question/Source 관계로 별도 검증하는 방향을 제안합니다. worker·relay·lookup에서 어떻게 검증할지 확정하고 schema/runtime/정상·음성 fixture를 일치시켜 주세요. 다른 방향이면 관련 계약을 함께 변경한 pin이 필요합니다. W4에서 검사를 완화하거나 W2 company를 null로 보내지 않았습니다.
2. **producer 채택:** pinned payload 사용, 로컬 current-context 제안, Core/non-Core 정책 책임 및 reason 목록, version 배정과 durable outbox 책임을 확정해 주세요. `QUESTION_EVIDENCE_REQUIRED`는 가상 예시이며 채택된 정책이 아닙니다.
3. **수신·권한·중복:** 인증 principal/channel, 문항 소유권과 Source 관계, 현재 입력/권한 조회 경계, 같은 message ID의 다른 본문·동일 version 경쟁의 거부 규칙, 취소·삭제 뒤 receipt와 가시성을 확정해 주세요. W4 코덱 통과만으로 서버 권한이 검증되는 것은 아닙니다.
4. **CT-12 인계:** 접근 가능한 runbook 경로/full SHA, 격리 owner/자료, private endpoint·queue 설정 변수명과 안전한 주입 주체, 준비·정리 책임을 제공해 주세요. 자격증명·DSN·token은 회신 파일에 넣지 않습니다.

W4의 로컬 준비는 완료했으나 이 문서만으로 R3-05 전체 채택 완료나 W1/W2 통합 완료를 선언하지 않습니다. W1의 W3 회신 취합, W2 T059 실행 재개 증거·접속 환경·CT15 runbook 및 T067 삭제 미구현은 별도 상태로 관리해 주세요.
