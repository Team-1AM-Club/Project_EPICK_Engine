# W4 피드백 반영 · 서비스 연결 계약 초안

2026-09-09. 기업 근거 연결, 서버 소유 입력, 정책 재검사, 가상 HTTP 통합 테스트를 추가했다.
이 문서가 새 서비스 연결 기준이다. 과거 `create_router`와 `w4-detailed-input/0.1`은 로컬 가상 데모용으로 보존한다.
새 서버에는 **`create_service_router`만** 등록한다. 같은 URL에 두 router를 함께 등록하지 않는다.

## 바로 재현하기

Python 3.10 이상. 저장소 또는 전달 ZIP의 루트에서 실행한다.

```text
uv sync --locked --extra api --extra test
uv run --locked --extra api --extra test python scripts/verify_service_handoff.py --output-dir output/ci/local-01
```

uv 0.12.0을 사용하며 매 실행에 새로운 출력 폴더를 지정한다. [CI 및 결과 기록 안내](w4-service-ci.md)를 참조한다.
개별 명령은 `uv run --locked --extra api --extra test python -m unittest discover -s tests -q`와
`uv run --locked --extra api --extra test python scripts/demo-service-handoff.py`다.
이 통합 데모는 서버와 모델을 모두 가상 구현으로 주입한다. API 키·GPU·외부 서버는 필요 없다.
모델의 실제 추론 정확도 평가는 [이전 v4 보고서](w4-review-v4-2026-09-09.md)의 별도 결과다.
이번 변경은 새 실제 모델 비교나 운영 모델 승인이 아니다.

개별 시연 명령의 기본 출력(통합 검증 도구는 지정 폴더의 `demos/`에 저장):

- `output/service-handoff-20260909/synthetic-company.json`: 명시적 가상 기업 진술 1개·우대 조건 1개와 가상 경험의 연결.
- `output/service-handoff-20260909/diagnostic-company.json`: 원본 SK하이닉스 진단 샘플의 근거 사용 거부와 제한 표시.

첫 결과의 VERIFIED/USABLE은 테스트 분기를 실행하기 위한 **가상 W3 판정**이다. 실제 SK하이닉스 사실을 검증했다고 표시한 것이 아니다.
두 결과 모두 경험 3개에 추출 3회·판단 3회의 모의 호출을 한다. 실제 모델 호출은 0회다.

## 피드백 항목별 반영

| 항목 | 코드·반환 내용 | 남은 연결 |
|---|---|---|
| W3 근거 연결 | `company_context.py`가 허용된 기업 진술·조건과 출처를 연결. 후보별 `company_support`, `used_company_refs` 반환 | W3가 이 로컬 투영 초안과 실제 계약의 대응을 검토 |
| 소유권 | HTTP 본문에서 owner·Episode·Snapshot 금지. 사용자 범위 조회 결과만 엔진에 전달 | Backend의 실제 인증·DB 조회 |
| 정책·삭제 | 매 모델 호출 전 PROCESS/SEND_TO_PROVIDER, 반환 전 PROCESS/RETURN_TO_CALLER. 매 경계에서 서버 문맥 재조회 | W1/Backend의 실제 동의·삭제·권한 판정 |
| SourceReview | 게시일 미상·JD 미파싱 등 제한을 응답에 보존. 기업 근거 없음을 자격 미달로 해석하지 않음 | 새로 검증된 출처 버전의 갱신 |
| 작업 상태 | `processing_status` 반환. W1 Job 상태를 직접 생성·갱신하지 않음 | 상태 대응표 승인 |
| 정렬 | 기존 상태 → 근거 종류 수 → ID 유지. 기업 연결을 가산점으로 쓰지 않음 | PO 승인 `PENDING_PRODUCT_REVIEW` |

## HTTP 요청과 서버 내부 입력

`POST /w4/recommend-from-raw`의 공개 본문은 [요청 샘플](../samples/service-handoff/request.json)처럼 아래 필드만 받는다.

```json
{
  "schema_version": "w4-service-input/0.1",
  "request_id": "synthetic-service-review-v1",
  "project_id": "project-demo-sk-hynix",
  "question": {
    "scope_id": "skhynix-2026-march-R260521-IT",
    "question_id": "expertise",
    "user_theme": null
  },
  "top_k": 3
}
```

`user_id`, `owner_id`, `episodes`, `snapshot`, `data_kind`, 회사 묶음, 모델명·키·URL을 추가하면 422다.
`scope_id`도 해당 서버 프로젝트의 `question_scope_id`와 같아야 한다. 문항 문구·글자 수·필수 여부는 현재 초안 상태다.
`self_description`에 주제가 없으면 모델을 부르지 않고 NEEDS_INPUT을 반환하되, 결과 반환 정책은 확인한다.

검증 모델과 JSON Schema는 같은 [Python 계약](../epick_w4/handoff_contract.py)에서 생성한다.

| 스키마 | 경계 |
|---|---|
| [service-input](../schemas/w4-service-input.schema.json) | 외부 HTTP 요청 |
| [server-context](../schemas/w4-server-context.schema.json) | Backend가 사용자 범위에서 조회한 내부 입력 |
| [knowledge-bundle](../schemas/w4-knowledge-bundle.schema.json) | W3 결과의 로컬 소비 투영 초안 |
| [detailed-output](../schemas/w4-detailed-output.schema.json) | 상세 추천 0.2 결과 |

ServerContext에는 `context_version`, 서버 소유 project·snapshot·episodes·excluded_episode_ids, 문항 범위와 기업 문맥이 있다.
동일 ID·버전에서 원문이 바뀌어도 문맥 해시 비교가 감지한다. 다만 `context_version`을 매번 임의로 생성하지 말고 서버 상태의 안정된 리비전으로 제공해야 한다.
소유자 불일치·중복 경험·제외된 경험 포함·스냅샷 버전 불일치는 잘못된 서버 입력으로 차단한다.
현재 한 번에 다루는 경험은 최대 20개, 합계 원문 50,000자다. 대규모 데이터에서 Graph·Vector로 후보를 좁히는 연결은 후속 범위다.

## 호스트 주입 계약

```python
from epick_w4.api import create_service_router

app.include_router(create_service_router(
    authenticate=authenticate,
    backend=backend,
    client_factory=make_judgment_client,
    extraction_client_factory=make_extraction_client,
))
```

authenticate는 검증된 세션/JWT의 사용자 ID를 반환하거나 호스트의 인증 오류를 발생시킨다.
Backend의 두 메서드는 동기식이며 thread pool에서 실행된다. ORM 세션 수명과 스레드 경계는 호스트가 관리한다.

```python
load_context(*, user_id, project_id) -> dict | None
authorize(*, user_id, project_id, context_version,
          action, provider, model) -> bool
```

`load_context`는 프로젝트·허용된 EpisodeVersion·제외 상태·Snapshot·W3 버전을 일관되게 조회한다.
권한 없는 프로젝트와 존재하지 않는 프로젝트는 모두 None을 반환한다. 전역 조회 후 클라이언트 owner_id를 대조하지 않는다.
`authorize`는 요청받은 리비전이 현재인지도 확인하고, 그 리비전에 대해 현재 정책·동의·삭제·철회를 확인한 경우에만 bool True를 반환한다.
provider/model은 SEND_TO_PROVIDER 때 서버 factory의 값이 전달된다. 다른 단계에는 None이다.

초기 PROCESS 확인 뒤, **각 추출·판단 호출 직전** 문맥을 다시 읽고 PROCESS와 SEND_TO_PROVIDER를 검사한다.
모든 계산이 끝난 뒤에도 다시 읽어 PROCESS와 RETURN_TO_CALLER를 검사한다.
문맥 변경은 409, 권한 상실/프로젝트 없음은 동일한 404, 정책 거부는 403이며 부분 추천을 반환하지 않는다.
상태 변경 후 자동 재시도하지 않는다. 새 Snapshot으로 재실행할지는 W1이 결정한다.

이것은 호출·반환 경계의 재검사다. 이미 전송된 원문의 회수나, 검사 이후 진행 중인 네트워크 요청의 원자적 취소를 보장하지 않는다.
실서비스의 처리 중 취소·공급자 보존·삭제 정책은 Backend/공급자의 별도 기능이 필요하다.

factory는 설정된 JsonClient를 구성하며 그 과정에서 원문 전송이나 추론을 시작하면 안 된다.
서비스 어댑터는 `content_logging_enabled=False`를 명시한 모델 클라이언트만 받는다.
LocalClient는 **`capture_traces=False`**로 생성한다. 기본 True는 기존 가상 비교 평가의 전문 보존용이며 서비스 경로에서는 거부된다.
원문 전문·모델 응답 전문은 오류 응답과 이 연결부의 로그에 남기지 않는다. 호스트의 인증·APM·프록시·공급자 로그 설정도 같은 계약을 따라야 한다.

## 기업지식 수용 규칙

`w4-knowledge-bundle/0.1`, `w3-w4-projection/0.1-draft`는 이번 W4 소비 투영 초안이다. 팀의 확정 W3 스키마를 새로 선언한 것이 아니다.
추출/정규화/restriction revision과 index ACK는 아직 없으며 [D-05 합의 요청](w4-d05-contract-decisions.md)에서 공동 결정 후 반영한다.
과거 일반 경로의 `ALLOWED`를 새 경로의 `USABLE`로 자동 변환하지 않는다. 상태 의미와 대응은 W3와 확인한다.

- 현재 VERIFIED + USABLE인 Claim·명시 Requirement만 고려한다. PREFERRED는 필수 조건으로 바꾸지 않는다.
- 기업·직무 scope, Snapshot의 SourceVersion 집합, SourceReview·Evidence 소속을 대조한다.
- 필수 출처가 LIMITED/UNAVAILABLE이면 이 투영에서는 기업 근거 전체 사용을 보류한다. 미파싱·검토 누락 출처도 쓰지 않는다.
- 게시일 미상은 제외한다. 접수 기간으로 게시일·유효기간을 보충하지 않는다. 게시일과 유효기간을 as_of와 대조한다.
- 유효기간의 시작/끝이 제공되지 않은 경우 추정하지 않고 진단을 보존한다. 범위 밖으로 확인되면 제외한다.
- ID 치환 자리, 중복 참조, 다른 출처의 Evidence는 거부한다. 원문·해시·의미 검증은 W3가 수행한 판정을 소비하는 것이며 W4가 다시 인증하지 않는다.
- accepted_refs는 입력에서 수용한 근거다. 후보의 used_company_refs는 모델이 해당 경험의 실제 원문 구간과 연결했고 코드 검사를 통과한 근거만 담는다.
- 모델이 없는 기업 ID·다른 경험 구간을 반환하면 요청을 실패 처리한다. 본인 행동 없이 결과·부정·타인 행동만 연결하면 AMBIGUOUS로 낮추고 used_company_refs에서 제외한다.

직무 연결 판단에는 현재 W3 문맥만 전달한다. 이전 로컬 catalog의 job_duties를 대신 사용하지 않는다.
기업 근거가 없으면 직무 연결은 NOT_SHOWN이며, 일반 문항의 경험 부합은 제한 상태로 평가할 수 있다.
company_support의 SUPPORTED는 소재의 관련성이다. 필수 지원 요건을 충족했다는 판정은 아니며 eligibility_assessment는 NOT_ASSESSED로 고정한다.

원본 SK하이닉스 `claim-handoff-sample/0.1-draft`를 정상 묶음으로 받지 않는다.
`project_diagnostic_handoff`는 이 파일을 **거부 상태로 투영**하면서 SourceReview의 제한만 보존한다.
manual_claim_examples나 `{{W2_...}}`를 기업 기준으로 변환하지 않는다.
9월 8일 별도 PDF 검토 기록은 [출처 검토 문서](skhynix-source-verification-2026-09-08.md)에 있다.
원본 샘플의 미파싱 상태를 그 기록으로 조용히 덮어쓰지 않는다. W3의 새 SourceVersion·Evidence·검증 결과로 연결해야 한다.

현재 REAL 경험 또는 REAL 기업 본문은 서버가 허용해도 차단한다. 외부 호출은 기존 가상 원문 해시와 고정 가상 기업 기준 해시를 모두 통과해야 한다.
사용자 요청의 SYNTHETIC 표시만으로 실제 정보를 보낼 수 없다. 실제 데이터 운영 전환은 별도 미완료 항목이다.

## W1 Job 상태 대응 제안 — 합의 전

| W4 processing_status | W1에서의 처리 제안 |
|---|---|
| COMPLETED | 공통 완료 상태로 연결하되 전체 작업의 다른 단계도 확인 |
| COMPLETED_WITH_LIMITATIONS | PARTIALLY_COMPLETED 후보. 제한 분석 허용·사용자 안내 정책과 함께 W1이 결정 |
| NEEDS_INPUT | 사용자 입력 요청. 이 문서는 새 W1 enum을 정의하지 않음 |
| NO_CANDIDATES | 검색/경험 보완 안내 여부를 W1이 결정. 지원 불가로 처리하지 않음 |
| HTTP 409 | Snapshot 갱신 및 재실행 여부를 W1이 결정 |
| HTTP 401/403/404 | 인증·권한·정책에 따른 중단. LLM 재시도 금지 |
| HTTP 422/502/503/504 | 입력·모델·서버 오류 구분 후 W1의 재시도 정책 적용 |

현행 초안 문항/정렬 정책 때문에 추천이 생성되면 COMPLETED_WITH_LIMITATIONS를 반환한다.
`job_state_mapping=OWNED_BY_W1_PENDING_AGREEMENT`, `ranking_policy_approval=PENDING_PRODUCT_REVIEW`를 유지한다.
계약과 테스트를 추가했다고 팀 합의나 운영 승인까지 완료된 것으로 표시하지 않는다.

## 파일별 역할

| 파일 | 기능 |
|---|---|
| [api.py](../epick_w4/api.py) | 공개 본문 검사·안전한 HTTP 오류·새 서비스 router |
| [service_adapter.py](../epick_w4/service_adapter.py) | 서버 조회·Snapshot 변경 감지·호출 전/반환 전 정책 검사 |
| [handoff_contract.py](../epick_w4/handoff_contract.py) | 입력·출력 검증 모델과 JSON Schema의 기준 |
| [company_context.py](../epick_w4/company_context.py) | W3 근거·날짜·범위·참조 수용과 진단 샘플 거부 |
| [company_detail.py](../epick_w4/company_detail.py) | 기업 연결 프롬프트, 실제 사용 근거 검사·응답 구성 |
| [detailed_recommendation.py](../epick_w4/detailed_recommendation.py) | 추출 → 상세 판단 → 근거 상태 → 순위 연결 |
| [w4_service_demo.py](../examples/w4_service_demo.py) | 가상 서버·정답 고정 모델 fixture. 운영 구현/실제 LLM이 아님 |
| [test_handoff_service.py](../tests/test_handoff_service.py) | 새 계약·HTTP 통합·권한·정책·기업 참조 회귀 검사 |
| [demo-service-handoff.py](../scripts/demo-service-handoff.py) | 외부 호출 없는 HTTP 시연 실행 |
| [prepare-service-handoff.py](../scripts/prepare-service-handoff.py) | 고정 가상 샘플·스키마 생성. 데모 실행 전에 다시 생성할 필요 없음 |

기존 전체 epick_w4 패키지, tests, samples, schemas와 의존성 설정을 함께 전달해야 한다.
모델 가중치·비밀키·.venv·개인 백업은 전달물에 포함하지 않는다.
