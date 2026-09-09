# W4 로컬 입력·출력 계약 초안

상태: 개발용 제안. 팀의 공개 API, W1~W3 계약, 기존 Job enum을 변경하지 않는다.
실행 가능한 전체 입력 예시는 `samples/w4_collaboration.json`을 참조한다.

## 호출 경계

```python
from epick_w4 import recommend

result = recommend(payload, user_id=authenticated_user_id)
# 선택 사항: 호출자가 제공하는 JSON 의미 판단 어댑터. Solar는 명시적으로 선택한다.
# result = recommend(payload, user_id=authenticated_user_id, llm=client)
```

인증 사용자 ID는 호출자가 별도 주입한다. CLI의 `--user-id`는 로컬 개발 편의 기능이며 인증 구현이 아니다.
FastAPI 연결부는 `POST /w4/recommend`와 `POST /w4/extract-evidence`를 제공한다.
인증·실제 서버·추천 Run DB 저장·Job 큐·최종 소재 선택 저장은 호스트 백엔드에서 연결해야 한다.
아래는 이미 Fact가 구성된 추천 입력이다. 원문부터 시작하는 별도 계약은 [근거 추출 안내](w4-evidence-extraction.md)를 참조한다.

## 입력

| 필드 | 의미 |
|---|---|
| `schema_version` | `w4-recommendation-input/0.1` |
| `request_id`, `data_kind` | 요청 식별자, `SYNTHETIC` 또는 `REAL` |
| `project` | 프로젝트·소유자·기업·직무·채용공고 버전 |
| `snapshot` | 스냅샷 ID, 기준일, 문항 ID/버전, 경험 ID→버전, 허용 SourceVersion ID 목록 |
| `question` | 문항 ID·버전·원문 |
| `episodes` | 경험 목록. 초기에는 전달받은 목록 전체를 검색 |
| `excluded_episode_ids` | 추천 제외 경험. 생략하면 빈 목록 |
| `company_context_policy` | 명시적으로 `OPTIONAL` 또는 `REQUIRED` |
| `unknown_date_policy` | `EXCLUDE`가 기본. 명시적인 `INCLUDE_WITH_LABEL`은 게시일 미상 표시 후 활용 |
| `company_knowledge` | 아래의 기업 맥락 계약. 빈 객체는 기업정보 미제공 |
| `top_k` | 최종 후보 개수. 기본 3, 1~20 |

`REAL`은 데이터 종류 표기다. 이 값을 바꿔도 프로토타입이 운영 준비 상태가 되거나 검증이 수행되지는 않는다.

### Episode와 근거

Episode는 `episode_id`, `version`, `owner_id`, `activity_id`, `title`, `raw_text`, `facts`를 가진다.
Fact는 `fact_id`, `kind` (`ROLE`/`ACTION`/`RESULT`), `text`와 다음 근거 참조를 가진다.

```json
{
  "episode_id": "episode-team-api",
  "episode_version": 1,
  "start": 24,
  "end": 69
}
```

위치는 Python Unicode 코드 포인트 기준의 시작 포함·끝 제외 범위다. UTF-8 바이트나 JavaScript UTF-16
인덱스를 그대로 전달하면 안 된다. `raw_text[start:end] == text`를 검사한다.
Paraphrase를 원문 발췌로 취급하지 않는다. 잘못된 기술명·수치·범위의 진술은 추천 근거에서 제거한다.
원문 일치는 사용자가 기록한 내용과의 일치이며, 실제 수행 사실 또는 성과 인과관계의 독립 검증이 아니다.

### 기업 맥락

`schema_version=w4-company-context/0.1`, `data_kind`, `company_id`, `source_versions`, `evidence`, `claims`를 받는다.
SourceVersion에는 실제 `source_version_id`, `source_id`, `company_id`가 있어야 한다.
Evidence에는 `evidence_id`, 소속 `source_version_id`, `exact_quote`, 보존 위치 설명 `locator`가 필요하다.

Claim 소비 조건:

1. `verification_status=VERIFIED`, `usage_status=ALLOWED`, `usable_for_matching=true`.
2. 실제 SourceVersion이 입력과 현재 Snapshot에 있으며 모든 Evidence가 그 버전에 소속됨.
3. 기업·직무·채용공고 버전이 현재 프로젝트 범위와 일치함. 직무/공고가 null이면 기업 수준 맥락으로만 취급.
4. 제공된 `valid_from`/`valid_to`가 기준일과 충돌하지 않음. 게시일·접수일로 유효기간을 생성하지 않음.
5. 게시일 미상은 호출자의 명시적인 활용 선택이 없으면 제외. 선택이 있어도 원문/검증 상태 조건은 유지.

`CONTRACT_SAMPLE_DIAGNOSTIC`, `SAMPLE_DIAGNOSTIC`, `production_usable=false`는 기업 입력 전체를 사용하지 않는다.
기업 진술 일부가 거부되면 다른 사용 가능 범위는 유지하며 진단 코드를 반환한다.
`explicit_requirements`에 대한 지원 자격 판정은 첫 버전 범위에 포함하지 않는다.
빈 목록을 요구사항 없음 또는 지원자 미충족으로 해석하지 않는다.

## 네 모듈의 연결

```text
Request와 인증·Snapshot 확인
 ├─ QuestionAnalyzer.analyze(question_text) → QuestionAnalysis
 └─ consume_knowledge(request) → 허용된 기업 Claim·근거와 진단 결과
        ↓
CandidateRetriever.retrieve(request, analysis, user_id) → Candidate 목록
        ↓
CandidateValidator.validate(candidate, request, analysis, user_id) → ValidatedCandidate
        ↓
RecommendationComposer.compose(validated, analysis, knowledge, top_k) → 추천 후보 목록
```

검색기는 소유권·제외·버전을 먼저 확인한다. 검증기는 검색 구현이 교체되어도 같은 조건을 다시 확인한다.
후보 수 제한은 검증과 정렬 이후에 적용한다. 기업 원문 검증을 수행하는 W3와 사용자 경험을 검증하는
Candidate Validator는 서로 다른 경계다.

## 출력

`schema_version=w4-recommendation-output/0.1` 결과는 다음을 가진다.

- `question_analysis`: 문항 기준과 기준을 추출한 원문 위치, 명시적인 답변 요구, 제한사항.
- `company_context`: 사용 가능 여부, 채택 Claim ID, 누락·범위·시점 진단.
- `candidates`: 경험 ID·버전, 순서, 상태, 문항 부합/누락 기준, 추천 이유, 강점, 한계, 확인할 사항,
  경험 원문 발췌와 별도로 구분된 기업 Claim·Evidence.
- `eligibility_assessment`: 항상 `NOT_ASSESSED`. 후보의 관련성과 지원 자격은 분리.
- `snapshot`: 입력의 스냅샷 ID·기준일·문항/공고 버전, 실제 검색한 경험 버전, 인용한 기업 SourceVersion.
  다른 사용자·제외 경험 ID는 이 메타데이터에도 노출하지 않음.

후보 상태의 초기 결정 규칙:

| 상태 | 기준 |
|---|---|
| `DIRECT_MATCH` | 모든 문항 기준이 허용된 본인 행동 발췌와 연결되고 필수 근거가 있으며 검증 이슈 없음 |
| `PARTIAL_MATCH` | 일부 문항 기준과 연결되고 검증 이슈는 없으나 다른 문항 기준의 행동 근거 부족 |
| `NEEDS_CONFIRMATION` | 근거 불일치, 본인 역할 불명확, 필수 근거 누락 등 추가 확인 필요 |

정렬은 후보 상태 → 문항 기준 충족 개수 → 근거 종류 충실도 → 기업과 겹치는 기준 개수 → 경험 ID 순이다.
같은 근거에서 Claim 수만 늘어도 독립 근거로 가산하지 않는다. 가중치나 LLM 점수는 도입하지 않았다.

실행 상태는 `COMPLETED`, `COMPLETED_WITH_LIMITATIONS`, `NO_CANDIDATES`, `NEEDS_INPUT`의 로컬 enum이다.
입력 계약 오류는 `ContractError(code, field)`로 반환하며 CLI 종료 코드는 2다.
정상 실행 결과의 `NEEDS_INPUT`은 코드 실행 실패가 아니라 데이터/해석 확인이 필요한 상태다.

## 아직 확정하거나 검증하지 않은 항목

실제 W1/W2/W3 연동, 운영 인증·권한 원장, 자유로운 문항/경험의 의미 정확도, LLM 응답 계약의 실 모델 준수율,
Graph·Vector 검색 품질, 실제 채용공고의 자격 충족 판정은 별도 통합·평가가 필요하다.
이 계약을 팀과 합의한 뒤 실제 백엔드·저장소와 통합한다.

## 의미 판단 어댑터 확장

입력·출력 schema_version 및 후보 상태는 유지한다. `llm`은 신뢰된 호출 코드가 주입하고
요청 JSON에서 모델 설정이나 API 키를 받지 않는다. 현재 경로는 가상 데이터만 지원한다.
`SolarClient`와 선택형 FastAPI 연결부를 제공한다. 현재 검증은 모의 응답 기반이며 키 미발급으로
실제 모델 응답은 확인하지 않았다. 전송 내용은 `synthetic_allowlist.json`의 가상 샘플로 한정한다.

- `question_analysis.method=llm_question_analysis/0.1`: 어댑터의 문항 기준과 실제 원문 인용을 연결.
- `pipeline_version=w4-semantic/0.1`: 의미 판단 경로. 실제 모델 호출 여부는 `inference.mode`로 구별.
- `inference.mode=SIMULATED_LLM`: 미리 작성한 모의 응답. `LLM`은 실제 클라이언트가 주입된 경우에만 사용.
- `inference`: 모델·공급자·프롬프트 버전, 호출 단계, 프롬프트/입력 해시. 원문 전문이나 내부 사고 과정은 기록하지 않음.
- 후보의 `reasons[].assessment_method=llm_evidence_matching/0.1`: 의미 연결 판단을 거쳤다는 표시.
  설명은 코드가 해당 원문 발췌를 조립하며, 모델이 새 경험 사실이나 점수를 생성하지 않음.
- `LLMError(code, stage)`: 모델 응답 계약 위반과 호출 실패를 표현. 규칙 결과로 조용히 대체하지 않음.

규칙 모드의 기존 응답 형태와 CLI 동작은 유지한다. 상세 규약·제한은 [LLM 연결 안내](w4-llm.md)를 참조한다.

## 선택형 HTTP 연결부

`create_router(authenticate=..., client_factory=...)`가 `POST /w4/recommend`를 제공한다.
본문은 위 입력 JSON 그대로이며 정상 응답은 동일 출력 JSON이다. 파일 경로를 받지 않는다.
인증 의존성은 신뢰된 사용자 ID를 반환해야 한다. 요청 본문의 `user_id`, 모델 이름, API 키로 설정을 변경하지 않는다.
현재 소유권 검사는 인증 ID와 전달된 데이터의 소유자 비교다. 실제 DB의 프로젝트 접근 권한과
Snapshot/경험 소유권 확인은 백엔드에서 이 함수를 호출하기 전에 수행해야 한다.

요청 본문은 실제 수신 바이트 기준 1,000,000바이트로 제한한다. 모델 통신은 작업 스레드에서 실행한다.
오류는 원문 대신 `{error, field}` 또는 `{error, stage}`를 반환한다.
인증 누락 401, 권한/전송 범위 위반 403, JSON 오류 400, 계약 오류 422, 큰 입력 413,
모델 설정/호출 한도 503, 모델 시간 초과 504, 나머지 모델 응답·통신 오류 502를 사용한다.
해당 경로는 내부 통합 초안이며 상시 서버 실행이나 팀 API 계약 확정을 의미하지 않는다.
