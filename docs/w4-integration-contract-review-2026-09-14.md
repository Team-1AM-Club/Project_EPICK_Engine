# W4 후보 판단·Snapshot·분석 결과 연결과 W3 추가 회신 검토

작성일: 2026-09-14. 상태: **팀 합의용 변경 제안 — 미채택, 신규 계약 미구현**.

현재 W4가 제공하는 계약을 먼저 고정하고, W3가 제공할 사용 가능 신호와 W1의 분석 결과 저장·무효화 계약을 함께 합의해야 한다. 경험 후보의 문항 부합, 기업 근거의 사용 가능 여부, 지원자의 전체 지원 자격은 서로 다른 판단이다.

이 문서는 사용자의 요청에 따라 첨부 요청서를 읽고 작성한 로컬 검토 자료다. W3의 미확인 계약을 정본으로 선언하거나 기존 Schema를 변경하지 않는다. 아래의 ‘채택 필수’는 **W4 관점에서 제안하는 보장 조건**이며 팀이 승인한 결정이 아니다.

## 1. 불러온 백업과 확인 범위

- 최신 백업: `20260913T164228.185138Z-15b059d8`, 한국시간 **2026-09-14 01:42:28**.
- 아카이브 1,624개 파일의 해시 검사 통과. 현재 파일과 1,622개 일치, 누락 0개. 이전 실패 실행의 오류 JSON·서버 로그 2개만 달라 현재 파일을 유지했다.
- 주 작업 폴더는 `feat/w4-recommendation-pipeline`, HEAD `d9e31822e2a031b41a303f05ad1e96d29fa09d8f`이며 기존 미커밋 변경이 있다.
- 전달용 검토 worktree는 `feat/w4-service-handoff`, HEAD `e336a6e619730cd5d3cb6d0e13f7209f69adb1bf`이고 검토 시 clean이었다.
- 백업에 보존된 [CI 검증 기록](../output/ci-github-20260909/verification.json)은 Windows·Ubuntu 각각 테스트 256개와 가상 HTTP 시연 2개 통과다. 이번 검토에서 원격 상태를 새로 조회하거나 CI·모델을 재실행하지 않았다.
- 현재 W4의 `w3-w4-projection/0.1-draft`는 팀 미채택 소비 투영이다. 실제 W1 저장·인증 통합, REAL 입력 허용, 운영 모델 선정은 완료되지 않았다.

검토 입력은 [W3 추가 회신 요청 내용 사본](inputs/W3_followup_request_2026-09-14.md)이다. 제공 경로는 `C:/Users/lis29/Downloads/W3_followup_request_2026-09-14.md`, 원본 SHA256은 `ab2cb1f9f0d3f724f8cc3034e65952386000c6a2ea1a65cbd215ceee98820b90`이다. 사본은 줄바꿈 형식을 정규화해 보존한 텍스트다.

요청서는 `w3-restriction/0.1-draft`의 채택 판단 자료를 요구한다. 이 버전의 **W3 schema·fixture·runbook 원문과 W1 D-06/D-07 본문은 현재 작업 폴더에서 확인하지 못했다.** 따라서 W3의 정확한 필드·enum·IndexKey 구성·응답 코드는 미확인이다. 아래 W3 표의 ‘현재 draft 규칙’은 요청서에 적힌 항목을 뜻한다.

백업에 저장한 작업 순서는 다음과 같다.

1. **기업 채용정보 수집·검증:** 요구사항·우대사항·평가 방향을 출처로 확인하고, 앞단 담당자가 W4에 전달한다.
2. **경험 선택 기준 정리:** 문항의 역량·조건과 기업정보를 연결하고 기준별 출처를 남긴다.
3. **경험 원문에서 근거 추출:** 경험별 본인 역할·행동·결과와 원문 위치·문맥을 보존한다.
4. **근거 검사와 적합성 판단:** 원문 일치와 의미 부합을 검사하고 관련·부분 관련·확인 필요를 구분한다.
5. **우선순위 결정과 추천:** 합의한 기준으로 정렬하고 추천 이유·부족한 근거를 반환한다.

현재는 상세 기준·실제 가상 원문 LLM 시연·서비스 DTO까지 연결한 상태다. 이번 요청은 이 흐름을 팀 서비스의 Snapshot·정책·저장 결과에 연결하는 계약 검토다.

## 2. 경험 후보와 전체 지원 자격의 구분

여기서 ‘후보’는 자소서 소재로 추천하는 **경험**을 뜻한다. 계약 자체가 ‘채택 후보’라는 의미와도 구분한다.

| 판단 대상 | 현재 정본 필드·값 | 허용되는 해석 | 이 값만으로 판단할 수 없는 것 |
|---|---|---|---|
| 경험의 문항 부합 | `candidates[].status`: `DIRECT_MATCH`, `PARTIAL_MATCH`, `NEEDS_CONFIRMATION` | 현재 문항 점검에 경험 원문이 어느 정도 부합하는지 | 지원자 전체의 입사 자격·합격 가능성 |
| 세부 내용의 근거 | `content_checks[].status`: `SUPPORTED`, `NOT_SHOWN`, `AMBIGUOUS`, `CONTRADICTED` | 해당 경험의 인용·문맥에서 확인한 근거 상태 | `NOT_SHOWN`을 실제 경험 부재로 단정, 실제 수행 사실의 독립 인증 |
| 경험과 기업정보의 연결 | `company_support[].status`: `SUPPORTED`, `AMBIGUOUS` | 기업 진술·요건과 본인 행동의 관련성 | `REQUIRED` 요건을 포함하더라도 전체 필수 요건을 충족했다는 판정 |
| 기업 근거의 수용 상태 | `company_context.status`: `AVAILABLE`, `LIMITED`, `UNAVAILABLE` | 이번 분석에서 사용할 수 있는 기업 근거의 범위 | 기업 요구사항이 없다는 결론, 지원 자격 미달 |
| 전체 지원 자격 | `eligibility_assessment.status`: **`NOT_ASSESSED`만 허용** | 현재 W4가 전체 지원 자격을 평가하지 않았음 | `ELIGIBLE`·`INELIGIBLE`로 자동 변환 |
| 처리 완료 여부 | `processing_status` | 계산·입력·제한 상태 | 지원 가능 여부 또는 W1 Job 전체 완료 |

현재 후보 판정은 다음과 같다. 불명확하거나 모순인 점검이 있거나, 충족 점검이 없거나, 사용 가능한 본인 행동이 없으면 `NEEDS_CONFIRMATION`이다. 그 외 모든 점검이 충족되면 `DIRECT_MATCH`, 일부만 충족되면 `PARTIAL_MATCH`다. 정렬은 후보 상태 → 지원 근거 종류 수 → 경험 ID 순서이며 정책 승인은 대기 중이다.

실제 저장된 [가상 결과](../samples/service-handoff/results/synthetic-company.json)의 1위 학습 경험은 `DIRECT_MATCH`지만 전체 자격은 `NOT_ASSESSED`다. [기업자료 사용 불가 결과](../samples/service-handoff/results/diagnostic-company.json)에서도 같은 경험의 일반 문항 부합은 유지되고, 기업 근거 목록은 비어 있으며 전체 자격은 계속 `NOT_ASSESSED`다.

W1 화면도 ‘이 문항에 활용하기 좋은 경험’, ‘추가 근거 확인 필요’, ‘전체 지원 자격은 평가하지 않음’으로 구분한다. 전체 자격 평가를 추가하려면 별도의 전체 필수 요건 목록·범위 완전성·개인 자격 근거·검증 책임·미확인 처리 규칙을 먼저 합의해야 한다. 우대 요건이나 추천 점수로 이를 대신하지 않는다.

## 3. 지금 제공할 수 있는 W4 계약·fixture·runbook

아래는 전달 커밋 `e336a6e619730cd5d3cb6d0e13f7209f69adb1bf`의 W4 기준이다. 버전 번호에 draft가 없는 파일도 팀 채택이나 운영 승인을 뜻하지 않는다.

| 구분 | 정본 경로 | 버전·역할 |
|---|---|---|
| 실행 타입 정의 | [handoff_contract.py](../epick_w4/handoff_contract.py) | `ServiceRequest`, `ServerContext`, `KnowledgeBundle`, `ServiceOutput`; JSON Schema 생성 기준 |
| 공개 요청 | [w4-service-input.schema.json](../schemas/w4-service-input.schema.json) | `w4-service-input/0.1` |
| 서버 조회 입력 | [w4-server-context.schema.json](../schemas/w4-server-context.schema.json) | `w4-server-context/0.1` |
| W3 소비 투영 | [w4-knowledge-bundle.schema.json](../schemas/w4-knowledge-bundle.schema.json) | `w4-knowledge-bundle/0.1`, 내부 계약 `w3-w4-projection/0.1-draft` |
| 추천 결과 | [w4-detailed-output.schema.json](../schemas/w4-detailed-output.schema.json) | `w4-detailed-output/0.2` |
| 요청·서버 fixture | [request.json](../samples/service-handoff/request.json), [server-context.synthetic.json](../samples/service-handoff/server-context.synthetic.json), [server-context.diagnostic.json](../samples/service-handoff/server-context.diagnostic.json) | 해당 커밋의 고정 가상 입력 |
| 결과 fixture | [synthetic-company.json](../samples/service-handoff/results/synthetic-company.json), [diagnostic-company.json](../samples/service-handoff/results/diagnostic-company.json) | 동일 커밋의 모의 응답 결과; 모델 성능 정답 아님 |
| 연결 runbook | [w4-service-handoff.md](w4-service-handoff.md), [w4-service-ci.md](w4-service-ci.md) | 공개 API·호스트 주입·재현 절차 |
| 계약 검사 | [test_handoff_service.py](../tests/test_handoff_service.py), [verify_service_handoff.py](../scripts/verify_service_handoff.py) | 가상 Backend·HTTP·정책 경계와 전체 검증 |
| 기존 미결 사항 | [w4-d05-contract-decisions.md](w4-d05-contract-decisions.md) | revision·Evidence·ACK·상태 대응 공동 합의 요청 |

W3는 자기 저장소의 **schema 경로 + schema version + 고정 commit 또는 태그 + fixture 경로·예상 결과 + runbook 경로**를 같은 방식으로 회신해야 한다. 이 목록이 없으므로 현재 W4 파일을 `w3-restriction/0.1-draft`의 정본으로 지정할 수 없다. 채택한 경로와 버전은 팀 합의 기록에 명시하고 이후 수정은 새 버전의 변경안으로 관리한다.

## 4. Snapshot과 분석 결과를 연결하는 계약

### 4.1 현재 구현된 경계

`POST /w4/recommend-from-raw`는 클라이언트에서 `request_id`, `project_id`, 문항 선택, `top_k`를 받는다. 소유자·경험 원문·Snapshot·회사 묶음은 HTTP 본문에 넣을 수 없다. 인증 사용자는 호스트가 제공하고, Backend가 사용자 범위로 일관된 문맥을 조회한다.

| 연결 대상 | 현재 입력 | 현재 결과 | 보장·한계 |
|---|---|---|---|
| 프로젝트·요청 | `project.project_id`, 요청 `request_id` | `project_id`, `request_id` | 연결 식별자이며 `request_id` 중복 처리 저장 기능은 없음 |
| 경험 Snapshot | `snapshot.snapshot_id`, `snapshot.episode_versions` | `snapshot.snapshot_id`, `snapshot.extracted_episode_versions` | 결과의 버전 집합은 실제 추출된 경험 집합. 전체 입력 Snapshot을 대신하지 않음 |
| 경험 근거 | `episodes[].episode_id/version/raw_text` | 후보 `episode_id/episode_version`, 근거 `start/end/exact_quote` | 동일 경험 버전의 Python 문자열 슬라이스 `[start:end]`와 인용을 대조. UTF-8 바이트 위치·브라우저 UTF-16 위치로 바로 사용하지 않음 |
| 전체 실행 문맥 | `context_version`과 서버 문맥 | `server_context_version` | 매 호출·반환 경계에서 같은 문맥 해시와 정책을 재검사. 별도 의미별 revision·영구 저장 기능은 없음 |
| 문항 기준 | 문항 선택 + 서버의 catalog | `question_scope.scope_id/question_id/user_theme/catalog_sha256` | 현재 해석 초안의 버전을 식별; 공식 문항 인증 아님 |
| 기업 입력 | `company_knowledge.knowledge_bundle_id`, `input_version_refs.source_version_ids` | `company_context`의 대응 필드 | 기업 버전 집합은 현재 **경험 Snapshot 객체 밖**에 있음. 전체 W1 Snapshot에 고정하는 규칙은 추가 합의 필요 |
| 기업 근거 사용 | Claim·Requirement·Evidence·SourceVersion | `accepted_refs`, 후보별 `used_company_refs`와 `company_support` | 수용한 근거와 실제 연결한 근거를 구분. 이 목록만으로 전체 실행 입력을 재현할 수는 없음 |
| 분석·작업·저장 결과 | 현재 없음 | `analysis_id`, `job_id`, `result_id` 없음 | W1 저장 모델과의 대응은 미구현 |

다음은 기존 결과에서 뽑은 연결 필드 예시다. **완전한 ServiceOutput은 아니며** 전체 예시는 위 fixture를 사용한다.

```json
{
  "schema_version": "w4-detailed-output/0.2",
  "request_id": "synthetic-service-review-v1",
  "project_id": "project-demo-sk-hynix",
  "server_context_version": "synthetic-context-v1",
  "snapshot": {
    "snapshot_id": "synthetic-service-snapshot-v1",
    "extracted_episode_versions": {
      "v4-raw-cooperation": 1,
      "v4-raw-study": 1,
      "v4-raw-challenge": 1
    }
  },
  "eligibility_assessment": {"status": "NOT_ASSESSED"}
}
```

현재 서비스의 성공 응답은 분석 결과를 계산해 반환했다는 뜻이다. W1 DB 저장·Job 완료·사용자 화면 게시까지 완료했다는 ACK가 아니다.

### 4.2 추가 합의안: W1이 보관할 분석 결과 연결 정보

제안 식별자는 **`w4-analysis-link/0.1-proposal`**이다. 아래는 필드 의미 제안이며 현재 API의 허용 필드나 새 JSON Schema가 아니다. 기존 `ServiceOutput`에 임의로 덧붙이지 않고, W1이 관리할 저장 레코드와 W4 출력의 관계를 먼저 합의한다.

| 제안 정보 | 생성·관리 주체 | 연결 규칙 |
|---|---|---|
| `analysis_id`, `job_id`, `attempt`, `result_id` | W1 | 논리 분석·작업·실행 시도·저장 결과를 구분. 변경된 입력을 재분석할 때 기존 결과를 덮어쓰지 않음 |
| 인증 소유 범위 + `project_id` | W1 | 서버에서 결정. 개인 결과·캐시는 사용자와 프로젝트 간 공유 금지 |
| `request_id`와 요청 내용 해시 | W1 | 같은 요청 ID·같은 입력의 재전송 규칙을 정함. 다른 입력이면 기존 결과를 성공으로 재사용하지 않음 |
| `snapshot_id` + 전체 입력 버전 참조 | W1, 참조 대상은 W3/W4 | 허용 경험 버전·제외 상태, 문항/catalog 해시, 기업 bundle·Source/SourceVersion, 추출·정규화·Evidence revision 등을 고정. 동일 ID의 내용 교체 금지 |
| `server_context_version` 및 문맥 해시 | W1/W4 경계 | 결과가 실제 계산에 사용한 문맥과 일치해야 함. 최신 정책 검사도 별도로 필요 |
| 입력·사용 근거 의존 관계 | W1 저장, W3/W4 제공 | 후보 인용뿐 아니라 전체 입력 기업자료·문항·경험 집합과 연결. 순위나 제외 판단에 영향을 준 자료도 추적 |
| 실행 정보와 결과 Schema 버전·해시 | W4 출력, W1 저장 | 모델·프롬프트·정책 버전과 원 결과를 보존. 모델 선정 승인과 구분 |
| 현재 사용·표시 상태와 검증 토큰 | W1 + W3 현재 신호 | 결과 계산 당시의 이력과 현재 사용자에게 제공 가능한 상태를 분리. 불명확하면 재사용을 보류 |

W1/W3의 추출·정규화·Evidence revision과 토큰의 정확한 이름·자료형은 원문 계약을 받아 확정한다. 해시의 대상·직렬화도 합의해야 하며 동일한 SHA256 문자열만으로 다른 범위의 revision을 대체하지 않는다.

저장·반환 절차 제안:

1. W1이 인증 사용자 범위에서 개인 삭제·제외·정책과 W3 현재 사용 신호를 확인하고 입력 버전을 고정한다.
2. W4가 그 문맥으로 처리하고 각 모델 호출 전과 최종 반환 전에 현재 문맥·정책을 다시 검사한다. 이 부분은 현재 구현되어 있다.
3. W1은 반환된 프로젝트·Snapshot·문맥·경험 버전·기업 참조를 고정 입력과 대조한다. 실제 추출 집합은 입력 집합의 부분집합일 수 있고, 후보·인용은 추출 집합에 속해야 한다.
4. W1은 저장 결과를 게시 가능 상태로 바꾸는 시점에도 현재 개인 lifecycle과 W3 토큰을 확인한다. 버전 비교를 조건으로 한 저장 또는 동등한 일관성 장치로 **W4 반환 이후의 변경**을 놓치지 않는다. 구현 방법은 합의 대상이다.
5. 저장된 결과·캐시를 다시 읽을 때도 현재 토큰·권한을 검증한다. 실패한 과거 결과를 조용히 수정하거나 자동 재분석하지 않고 W1의 합의된 안내·재실행 정책을 따른다.

`processing_status`와 W1 Job enum은 별도로 대응한다. 현재 `COMPLETED_WITH_LIMITATIONS`를 `PARTIALLY_COMPLETED`로 연결하는 것은 제안일 뿐이다. `NO_CANDIDATES`와 회사 근거 사용 불가는 자격 미달로 바꾸지 않는다.

## 5. W3 요청서 형식에 따른 채택 판단표

모든 행은 **W3 원문 확인·팀 합의 대기**다. W1 D-05/D-06/D-07 중 어느 번호에 기록할지는 W1이 본문과 대조해 결정한다.

| 항목 | 현재 draft 규칙 | 채택 필수 여부 | 변경 가능 범위 | 영향 받는 W1/W2/W4 계약 |
|---|---|---|---|---|
| 정본 지정 | 요청서에는 `w3-restriction/0.1-draft`만 명시; 경로 미제공 | 재현 가능한 버전·경로·fixture 고정은 필요 | 저장소 구조·파일명·태그 방식 | W1 채택 기록, W2 생산 Schema, W4 소비 어댑터 |
| 이벤트·중복 처리 | `source.restriction.changed`, event ID와 payload 불변 dedup | 같은 이벤트의 재전송이 다른 효과를 만들지 않고 ID 충돌을 감지하는 의미는 필요 | 이벤트 이름·ID 형식·정규화/해시 표현. 같은 ID의 다른 payload를 덮어쓰는 변경은 불가 제안 | W2 outbox, W1/W4 무효화 통지 |
| Source 범위 순서 | Source-wide `aggregate_revision` | 같은 Source의 오래된 상태가 최신 제한을 되돌리지 못하도록 순서를 보장해야 함 | 필드명·자료형·동등한 순서 토큰. SourceVersion별 revision만으로 대체할 수 있는지는 별도 증명 필요 | W2 발행 순서, W1 Snapshot 의존성, W4 현재 제한 검사 |
| 상태·판정 이유 | `RESTRICTED`/`RELEASED`, accuracy/reason code enum | 제한 상태·검증 정확성·사용 가능 사유를 구분하는 의미는 필요 | enum 이름과 확장 규칙. 알 수 없는 값을 허용으로 간주하지 않음 | W2/W3 상태 생산, W4 `verification_status`·`usage_status` 대응 |
| stale·conflict·gap | fail-closed 처리 | 불일치·누락 상태에서 사용 허용으로 승격하지 않는 조건은 필요 | stale 무시/거부, 재조회·재처리 방식. 정상 중복까지 무조건 장애로 만들 필요는 없음 | W1 재실행/대기 안내, W2 재전송, W4 실행·반환 차단 |
| replay·snapshot | 복구 시 fail-closed | 완전성과 최신 제한을 확인하기 전 허용하지 않고 개인 삭제를 되살리지 않아야 함 | 복구 프로토콜·저장 형식·재처리 단위 | W1 개인 lifecycle, W2 복구 경계, W4 저장 결과 재사용 |
| IndexKey·ACK | 전체 `IndexKey` readback 뒤 ACK | 합의된 전체 영향 범위에 반영됐다는 증거가 필요. 접수 ACK와 사용 가능 ACK 구분 | IndexKey 구성·readback/동등한 증명·집계 방식. 일부 성공을 전체 성공으로 표시하면 안 됨 | W2 접수 결과, W1 작업 상태, W4 색인 사용 조건 |
| history·generation | `history_complete`, `generation` | 누락된 이력이나 다른 색인 세대를 정상 상태로 쓰지 않도록 검증 필요 | 필드명·세대 식별 방식. generation의 범위·비교법은 W3가 명시 | W1 결과/캐시 의존성, W4 현재 세대 비교 |
| 개인 삭제와 공개 제한 | 요청서가 구분·최소 신호 명시를 요구함 | 개인 삭제는 W1 private lifecycle로 유지하고 공개 Source 제한과 분리하는 안을 제안 | 비공개 명령·토큰·ACK 전달 방법. 공개 이벤트에 개인 ID/원문 포함 금지 제안 | W1 권한·삭제·표시, W3 개인 색인 존재 시 삭제 ACK, W4 전송·반환 |
| W4 usability DTO | 정본 DTO·캐시·generation 조건 요청; 원문 미제공 | 단순 `RELEASED`와 실제 근거 사용 허용을 구분하는 소비 계약 필요 | 아래 최소 정보와 기존 투영을 대응할 필드·Schema 버전 | W1 load_context/authorize, W4 기업 근거·저장 결과 사용 |

`RELEASED`는 Source 제한이 해제됐다는 축의 값으로 다루고, **검증 완료·색인 완료·개인 접근 허용을 한꺼번에 뜻하는 값으로 매핑하지 않는 안**이다. 현재 W4의 `USABLE` 또는 과거 `ALLOWED`와도 원문 대조 없이 자동 치환하지 않는다.

## 6. 개인 삭제·W3 복구·현재 사용 신호

### 6.1 두 종류의 Snapshot

- **W1 분석 Snapshot:** 어떤 경험·문항·기업자료 버전으로 분석했는지 고정하는 사용자 범위 입력이다.
- **W3 restriction 복구 snapshot:** 이벤트 이력과 Source 제한/색인 상태를 복구하는 자료다. 이것으로 사용자 경험·분석 결과의 삭제나 표시 상태를 복원할 수 없다.

과거 분석 Snapshot의 `as_of`를 기준으로 지금의 제한·삭제를 무시해서도 안 된다. 재현용 입력 시점과 현재 사용 권한은 별개다.

### 6.2 W1/W3가 교환해야 할 최소 신호 제안

| 경계 | 최소 정보·책임 |
|---|---|
| W3 → W1/W4 공개 기업자료 상태 | Source 식별자, 현재 제한 revision·상태, 정확한 버전/IndexKey 참조, history 완전성, generation, 색인 반영 증거, 검증/사용 사유 |
| W1 → W4 개인 접근 상태 | 인증 사용자·프로젝트 범위, 삭제/제외/권한/동의의 현재 revision, 각 처리·전송·반환 허용 여부. 현재 인터페이스는 `load_context`·`authorize` |
| W1 → W3 개인 파생 데이터를 W3가 보관하는 경우에만 | 비공개 삭제 명령 ID, 접근 제한된 대상 식별 범위, 재사용하지 않는 lifecycle revision/삭제 표식, 삭제 대상 버전·색인 범위. 원문·개인 ID를 공개 restriction 이벤트에 실어 보내지 않음 |
| W3 → W1 비공개 삭제 ACK | 같은 명령·대상·lifecycle revision, 전체 해당 색인/파생 데이터의 삭제 또는 조회 차단 반영 결과. 공개 Source 제한 ACK와 구분 |

W3가 공개 기업자료만 관리한다면 개인 Episode·사용자 ID를 받을 필요가 없다. W1이 개인 삭제 표식을 유지하고 W3의 공개 신호와 함께 권한을 판단하면 된다. 개인 색인을 실제로 관리하는 경우에만 별도의 private 경로가 필요하다.

공개 `RELEASED`, 늦은 이벤트, replay, 복구 snapshot 중 어느 것도 W1의 최신 삭제 표식을 해제할 권한을 갖지 않는다. 복구 과정에서 개인 삭제 이력을 확인할 수 없으면 해당 개인 데이터를 조회·게시 가능한 상태로 복구하지 않는 안을 제안한다. 삭제 표식·ACK의 보존 기간과 로그 최소화도 W1/W3가 정해야 한다.

### 6.3 W3 usability DTO에 요구할 최소 정보

아래는 **정본을 요청하기 위한 의미 목록**이다. 실제 DTO는 아직 제공받지 못했으므로 임의의 enum·IndexKey 필드로 완성된 W3 Schema를 만들지 않았다.

| 정보 | W4 소비에 필요한 의미 |
|---|---|
| 계약 버전·Source·적용 범위 | 어떤 버전의 신호가 어느 Source와 범위에 대한 것인지 검증 |
| 고정 지식 버전 참조 | SourceVersion, 추출·표현·정규화 revision, Claim/Requirement와 Evidence의 버전 연결 |
| 현재 `aggregate_revision`·restriction 상태 | 동일 Source의 최신 제한인지 확인. 오래된 해제 상태로 최신 제한을 덮어쓰지 않음 |
| accuracy/검증 상태·reason codes | 제한 해제와 내용 검증을 구분. 미지의 코드에 대한 보수적 대응 규칙 필요 |
| 전체 IndexKey와 ACK/readback | 이 분석이 필요로 하는 정확한 버전·색인 집합의 반영 완료 증거. 키 구성·완전성 기준은 W3가 제공 |
| `history_complete` | 누락·복구 중인 상태를 사용 허용으로 간주하지 않는 조건 |
| `generation` 및 그 범위 | 전역인지 Source/색인별인지 명시. 현재 값과 동일성 비교; 자료형을 모르면서 숫자 대소 비교하지 않음 |
| 현재성 확인 방법 | 권위 있는 조회 경로·검증 토큰·갱신 규칙. 관측 시각이나 TTL만으로 최신성을 보장하지 않음 |

사용 가능 조건 제안은 **현재 권한·개인 lifecycle 허용 AND 기업 근거 검증·범위/날짜 적합 AND 최신 restriction 허용 AND 이력·색인 완료 AND 정확한 버전/generation 일치**다. LLM이 이 정책 조건을 결정하지 않는다.

현재 W4 앱은 새 신호를 직접 받거나 generation을 검증하지 않는다. 지금 구현된 것은 서버 문맥 재조회·해시 비교와 호스트 `authorize` 호출이다. 새 신호는 W1/W3의 호스트 어댑터 책임과 W4 버전 변경안을 합의한 뒤 반영한다. 현재 Schema는 추가 필드를 거부하므로 문서의 제안 필드를 기존 요청에 바로 추가하면 안 된다.

### 6.4 저장 결과·캐시 무효화 조건 제안

1. 캐시에는 인증 범위, 프로젝트, Snapshot/문항/전체 경험 입력, 기업 Source·정확한 버전, 결과/실행 버전, 개인 lifecycle과 W3 generation/restriction 토큰의 의존 관계를 기록한다. `used_company_refs`만 추적하면 제외·정렬에 영향을 준 입력을 놓칠 수 있다.
2. Source 제한·철회, 개인 삭제·제외·권한/동의 변경, 경험 수정, 지식 재추출·정규화 변경, 문항 기준 변경, generation 변경 시 영향받은 저장 결과를 현재 결과로 재사용하지 않는다.
3. 이벤트 기반 무효화와 읽기 시점 검증을 함께 둔다. 이벤트 수신 지연·gap·신호 조회 실패·세대 불일치에서는 오래된 캐시를 성공 결과로 반환하지 않는다.
4. 과거 결과의 보존 가능 여부는 개인 삭제 정책을 따른다. 보존 가능한 계산 이력과 현재 화면의 사용 가능 상태를 분리하고, 원문 삭제 의무가 있는 결과는 이력이라는 이유로 본문을 남기지 않는다.
5. 재검증 전에는 과거 추천을 자동으로 다시 게시하지 않는다. 기업 근거를 제외한 제한 분석을 허용할지는 별도 정책이며, 허용하면 새 결과로 계산한다. 이를 전체 자격 미달로 표시하지 않는다.

## 7. W2 outbox 연결 시 producer·consumer 의미 제안

W2/W3의 실제 응답 DTO·HTTP 코드·outbox 상태 이름은 미확인이다. 다음 표는 합의할 의미이며 실제 enum을 선언하지 않는다. **전송 접수·상태 반영·W4 사용 가능**은 별도 단계다.

| 상황 | W2 producer가 보장할 조건 | consumer response의 성공/실패 의미 | 후속 처리와 W4 영향 |
|---|---|---|---|
| 신규 정상 이벤트 | 원 상태 변경과 이벤트의 유실 없는 기록, 같은 Source의 일관된 순서, 지원 Schema, 고정 event ID·payload | 접수 성공은 재시작 후에도 처리할 수 있도록 기록됐다는 의미. 전체 색인 반영 성공과 구분 | W2 전송 재시도 종료 조건을 접수 수준으로 정할지 명시. W4는 별도 현재 사용 신호 확인 |
| 전송 결과 불명·타임아웃 | 동일 ID·동일 payload로 재전송. 재시도마다 revision/ID를 새로 만들지 않음 | 성공 여부 미확정이며 자동 실패/사용 가능으로 단정하지 않음 | 같은 이벤트 조회/재전송으로 확인 |
| 동일 이벤트 중복 | 원 payload 불변 | 기존 접수/처리 결과를 반환. 부작용을 중복 적용하지 않음 | 처리 진행 상태를 원 이벤트와 함께 추적 |
| 같은 ID·다른 payload | 충돌 감지 가능한 비교 규칙 | 충돌 실패. 이전 이벤트 덮어쓰기 금지 | 격리·원인 확인. 오류 payload를 같은 ID로 계속 재시도하지 않음 |
| 오래된 revision | 최신 revision과 비교 가능한 Source 범위 식별 | 현재 상태를 유지하는 stale 응답. 적용 성공과 구분 | 오래된 RELEASED로 제한 해제 금지 |
| revision gap·이력 불완전 | 누락 이벤트 또는 합의된 복구 snapshot 제공 | 접수됐더라도 사용 가능 상태의 반영 완료는 아님 | 복구와 완전성 확인 전 사용 허용으로 승격 금지 |
| 잘못된 Schema·enum·범위 | 채택한 버전에 맞는 완전한 payload | 입력 거부. 정상 완료로 ACK하지 않음 | 생산 계약 수정·격리. 무한 재시도와 조용한 필드 폐기 금지 제안 |
| 색인 일부 실패·일부 readback | 이벤트와 영향 IndexKey/버전 범위를 추적할 수 있음 | 상태 접수는 성공할 수 있어도 전체 색인 완료 ACK는 실패/대기 | 실패 범위 재처리. 전체 필요 키 완료 전 W4 사용 가능 신호 금지 |
| 전체 readback 완료 | 동일 Source revision·generation·정확한 키 집합에 대응 | 합의된 색인 반영 완료. 개인 권한이나 내용 검증을 대신하지 않음 | 다른 검증·현재 제한·개인 lifecycle 조건까지 확인 후 소비 |

공개 outbox에 개인 삭제 이벤트를 섞지 않는 안이다. W3가 개인 파생 데이터를 보유할 때의 삭제는 앞 절의 private 경로와 별도 성공 기준으로 다룬다.

## 8. 공동 fixture로 닫아야 할 사례

아래 사례 ID는 이 검토 문서의 제안 ID이며 W3 정본 fixture ID가 아니다. ‘기존’은 관련 로컬 fixture·테스트와 저장된 CI 기록이 있다는 뜻으로, 실제 W1/W2/W3 통합을 이번에 실행했다는 뜻이 아니다.

| 사례 | 공통 입력·상황 | 확인할 결과 | 현재 근거 |
|---|---|---|---|
| F01 | 가상 정상 기업자료 + 학습 경험 | 후보 `DIRECT_MATCH`, 전체 자격 `NOT_ASSESSED`, 정확한 양쪽 근거·Snapshot 참조 | 기존 synthetic-company fixture |
| F02 | 기업자료 사용 불가 + 같은 일반 문항 경험 | 회사 근거 빈 목록·제한 표시, 전체 자격 `NOT_ASSESSED` | 기존 diagnostic-company fixture |
| F03 | 다른 소유자·중복/제외 경험·Snapshot 버전 불일치 | 잘못된 서버 경험 입력은 503, 접근 불가 프로젝트는 404; 모델 전송 전 차단 | 기존 ServiceTests |
| F04 | 모델 첫 호출 뒤 삭제·제외·원문/기업 상태 변경 | 409 `CONTEXT_CHANGED`; 후속 모델 호출·결과 반환 차단 | 기존 ServiceTests |
| F05 | 마지막 모델 호출 뒤 반환 정책 철회 | 403, 결과 본문 미반환 | 기존 ServiceTests |
| F06 | 동일 event ID의 동일/상이 payload | 중복은 원 처리 결과, 상이 payload는 충돌; 중복 효과·덮어쓰기 없음 | W3 fixture 필요, 미실행 |
| F07 | 최신 제한 뒤 오래된 RELEASED | 최신 제한 유지, 과거 캐시 게시 불가 | W3/W1 공동 fixture 필요, 미실행 |
| F08 | gap 또는 복구 이력 불완전 | 전체 완료/사용 가능으로 승격하지 않음 | W2/W3 공동 fixture 필요, 미실행 |
| F09 | IndexKey 중 하나만 readback 실패 | 부분 성공을 전체 완료로 ACK하지 않음 | W3 정본 IndexKey fixture 필요, 미실행 |
| F10 | 개인 삭제 완료 후 공개 RELEASED/replay/복구 snapshot | 공개 Source 상태가 바뀌어도 개인 데이터·추천 표시·캐시가 되살아나지 않음 | W1/W3 private fixture 필요, 미실행 |
| F11 | 저장 후 generation/restriction 변경 또는 현재 신호 조회 실패 | 기존 저장 결과를 현재 결과로 재사용하지 않음 | W1/W4 저장·캐시 fixture 필요, 미실행 |
| F12 | W4 최종 반환과 W1 결과 게시 사이의 삭제·제한 변경 | 조건부 저장/게시 검사에서 차단 | W1 실제 저장 fixture 필요, 미실행 |
| F13 | 동일 request ID 재전송 또는 다른 입력으로 재사용 | 승인된 중복 규칙 적용; 다른 입력에 기존 결과를 잘못 연결하지 않음 | W1 분석/Job 계약 필요, 미실행 |

각 공동 fixture에는 **고정 버전·초기 상태·이벤트 순서·모든 관련 IndexKey·개인 lifecycle·예상 응답·최종 저장/표시 상태**를 함께 둔다. 공개 fixture는 개인 정보 없이 작성하고, 개인 삭제 사례는 가상 private 자료로 분리한다. 모든 팀이 같은 fixture와 예상 결과를 검토한 뒤 실제 통합 검증으로 전환한다.

## 9. 다음 진행 순서와 회신 책임

1. **W4가 먼저 전달:** 이 문서의 후보/전체 자격 구분, 현재 4개 Schema, Snapshot 연결 필드, 결과 저장 계약 제안과 기존 fixture. 현재 구현과 미구현 항목을 함께 표시한다.
2. **W3가 보완:** 실제 `w3-restriction/0.1-draft` schema·fixture·runbook 경로와 고정 버전, 정확한 IndexKey·enum·ACK·generation 범위, 정본 usability DTO를 제공하고 5절 표의 규칙별 채택/변경 범위에 답한다.
3. **W1·W2와 공동 결정:** W1의 분석/Job/Snapshot 식별자·private 삭제·결과 게시·캐시 계약, W2의 outbox 접수/처리 완료 의미를 정한다. W1이 D-05/D-06/D-07 기록 위치와 수용 상태를 확정한다.
4. **불일치가 있으면 변경안을 먼저 승인:** 현재 W4 투영과 W3 정본의 필드 대응·누락·상태 전이를 표로 고정한다. 승인 전에는 enum 치환, 기존 결과 변경, Schema 확장으로 합의를 대신하지 않는다.
5. **채택 이후 구현·통합:** 확정 버전에 맞춘 어댑터와 회귀 사례를 반영하고, 공동 fixture 및 실제 W1/W2/W3 연결로 저장·삭제·복구·캐시까지 확인한다.

이 요청의 문서는 ‘후보 계약을 팀이 채택할 수 있는 판단 자료’를 요구한다. W4의 현재 계약과 변경 제안은 이 문서로 제공할 수 있고, W3 정본이 없는 부분은 미결 사항으로 명시한다. **현재 완료 범위는 백업 확인·기존 계약 대조·회신용 문서 작성이다. 신규 런타임 구현, 외부 회신, 푸시·PR·배포는 수행하지 않았다.**
