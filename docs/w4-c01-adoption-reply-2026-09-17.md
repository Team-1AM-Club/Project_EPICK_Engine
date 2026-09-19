# W4 → W3 C01 r2 적용 결과 회신 초안

**추가 검토:** [실제 모델 비교·API 시연](w4-c01-live-evaluation-2026-09-17.md)에서 총 42회를 호출했다. 분리 평가에서는 Gemma 12B가 우수했지만 통합 결과에 기업 기준 오연결이 남아 운영 선정은 보류했다. 아래 292개·모의 시연은 최초 C01 연결 검증이며, 후속 전체 회귀는 305개다. 현재 백엔드의 구체적인 연결 변경은 [W1 연결 계획](w4-w1-bridge-plan-2026-09-17.md)에 정리했다.

2026-09-17. **외부 전송·공동 채택 서명 전 초안.**

W3 커밋 `05f26b4c0a52aecf155a66df0fcaa38e6fbd4cf5` / `w3-c01/0.2-candidate/r2`에 맞춘 W4 consumer를 구현했습니다. 원본 Schema 5종과 W4 연결 fixture는 해시를 유지해 보존했습니다. W4 서버 입력 보완 계약과 출력 변경은 [적용 안내](w4-c01-integration-2026-09-17.md)에 명시했습니다.

이번 실행은 W4 전체 테스트 **292개 통과(기존 256 + C01 36)**, 기존 HTTP 시연 2개 통과, W3 실제 localhost HTTP 서버와 W4 API 연결 시연 **7개 통과**입니다. 실제 모델 호출은 0회이며, 모델 응답과 W2 event/기업 지식은 가상 자료입니다. 실제 W2 생산 코드와 W1 서비스 통합 완료를 뜻하지 않습니다.

| 항목 | W4 적용 결과 | 공동 채택에 남은 사항 |
|---|---|---|
| A1 DTO | signal/StructureResponse/ACK 원본 Schema로 검사. Source/Version·generation·Evidence 참조·요건 트리 검증, 원 상태와 위치 보존 | W4 보완 metadata의 공급 위치와 책임, 서버 입력 0.2/결과 0.3 수용 확인 |
| A2 순번/generation | 두 cursor를 별도로 보존하고 전체 IndexKey와 generation을 재검사. r1/외부 DB 혼용 차단 | W2/제품 책임자의 Source 단위 restriction 순번 최종 결정, 동일 commit/profile 배포 |
| A3 캐시 | 모든 입력 Source와 W1 사용자/프로젝트 범위를 의존성으로 추적. 제한·조회 실패·현재성 불일치 시 재사용 차단과 관련 캐시 삭제. 재색인 후 새 generation 지식으로 복구 | 실제 W1 결과 저장/게시 시점 검사와 서비스 다중 replica 운영 |
| A4 재전달/ACK | 트랜잭션 반영 후 ACK. 중복, ACK 유실, 재시작, 저장 실패 rollback, 동일 generation 충돌 검사 | host 재시도 worker/DLQ·재시도 횟수/간격. 처리 완료 ACK와 W1 게시 ACK는 별도 |
| A5 출처/보관 | static_html과 전체 추출키 보존. Source 만료와 명시적 cache TTL 제한, 상태 재조회 | 운영 TTL·유휴 purge·물리 삭제 정책 및 PM/W2/W4의 P4/P5 결정 |

W4 보완 metadata는 호스트가 정확한 Source/IndexKey에 연결한 채용 범위·원문 해시·게시일/유효 기간·파싱 상태·필수 자료 여부·만료 시각입니다. 누락 값을 추정해 채우지 않으며, 게시일/범위/해시가 미상인 근거는 사용하지 않습니다. 이 봉투는 W3 정본에 새 필드를 추가했다는 뜻이 아닙니다. 공급 위치와 의미를 함께 확인해 주세요.

Requirement의 AND/OR, 동일 경험 요구, 예외·비교 정보, GENERAL/REQUIRED/PREFERRED를 보존했습니다. 모델이 경험 하나의 LEAF별 근거를 제시하면 코드가 조건을 합산합니다. 전체 지원 자격은 계속 NOT_ASSESSED이며 새 프롬프트의 실제 모델 품질 평가는 남아 있습니다.

기술 방향은 현재 r2 기준으로 수용하도록 구현했지만 **공동 채택 완료로 표기하지 않습니다.** 위 metadata/출력 변경에 대한 W3/W1 검토와 순번 단위·P4/P5 결정, 실제 W2/W1 연결 결과를 함께 반영한 후 동일 revision에서 확정하면 됩니다.

검증 근거:

- [전체 회귀](../output/c01-integration-20260917/regression-2/summary.json)
- [전달 파일 해시와 최종 검증 기록](../output/c01-integration-20260917/implementation-verification.json)
- [W3→W4 시연](../output/c01-integration-20260917/http-demo-2/summary.json)
- [가상 추천 결과](../output/c01-integration-20260917/http-demo-2/recommendation.json)
- [W4 자체 소비 테스트](../tests/test_c01_integration.py)

W4의 이번 변경은 로컬 미커밋 상태입니다. 기존 원격 `e336a6e` 커밋이나 과거 CI 256개 결과를 새 C01 구현의 커밋/CI 근거로 사용하지 않습니다. 전달 시에는 새 변경의 파일 해시 기록을 함께 사용하고, 원격 전달 커밋은 별도로 지정해야 합니다.
