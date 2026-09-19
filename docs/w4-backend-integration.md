# W4 백엔드 연결 계약 — 2026-09-09 피드백 반영

**2026-09-17 최신 확인:** 백엔드에 추천 API와 저장 구조가 추가됐다. [현재 W1 연결 계획·실제 DTO 대조](w4-w1-bridge-plan-2026-09-17.md)를 먼저 읽는다. 아래의 비어 있는 `feat/BE` 파일 설명은 9월 9일 당시 기록이다.

**새 서비스 연결 기준은 [서비스 계약·실행 안내](w4-service-handoff.md)다.**
`create_service_router`가 서버 조회·정책 재검사와 W3 근거 투영을 적용한다.
요청은 `w4-service-input/0.1`, 서버 내부 입력은 `w4-server-context/0.1`, 출력은 `w4-detailed-output/0.2`다.
가상 통합 검증을 추가했으며 실제 팀 인증·DB 연동, 상태 대응·정렬 승인, 운영 모델 확정은 남아 있다.

## 아래는 기존 가상 데모 API 0.1 기록

기존 `create_router` 예시는 가상 데모용이다. 새 서비스에 그대로 등록하지 않는다.

엔진의 HTTP 연결부와 서로 다른 추출·판단 모델 주입을 구현했다. 팀 서비스와의 실제 인증·DB 연결은 아직 실행하지 않았다.

사용자가 알려 준 서비스 저장소의 `feat/BE`를 확인했다. 확인한 커밋은
[`712a4a1c357bd7189b8a7bcf6b640aeca657af58`](https://github.com/Team-1AM-Club/Project_EPICK_Service/tree/712a4a1c357bd7189b8a7bcf6b640aeca657af58/backend)다.
`backend/app/main.py`, `pyproject.toml`, `.env.example` 및 api·schemas·services 등의 `__init__.py`는 모두 0바이트였다.
원격 `develop`, `main`, `feat/FE`는 같은 초기 커밋 `6f7b016`을 가리켰다. 실제 엔드포인트·DTO·인증·DB 명세나 실행 서버 주소를 확인할 수 없었다.
참고 사본은 `output/service-reference-20260909-be/`에 보존했다. 서비스 저장소를 수정하거나 푸시하지 않았다.

## 호스트가 연결할 함수

```python
from epick_w4.api import create_router

# 아래 세 함수는 팀 서비스가 구현하거나 주입한다.
# authenticate: 검증된 세션/JWT에서 사용자 ID를 반환하는 FastAPI dependency
# make_judgment_client: 승인된 판단 모델의 JsonClient를 반환
# make_extraction_client: 승인된 추출 모델의 JsonClient를 반환
app.include_router(create_router(
    authenticate=authenticate,
    client_factory=make_judgment_client,
    extraction_client_factory=make_extraction_client,
))
```

모델 이름·공급자·URL·키는 서버 설정에서 결정하며 요청 JSON으로 선택하지 않는다. 현재 운영 모델 선정은 `WITHHELD`다.
실제 비교 정답·필수 검사·팀 검토를 통과한 조합이 준비되면 factory에 주입한다. 이번 데모의 Gemma 조합은 실험 후보다.
factory는 모델 호출 어댑터를 반환하는 경계다. GPU 모델을 적재·교체하는 스케줄러는 아니다.
5080 단일 GPU 시연은 [실행 스크립트](../scripts/run-staged-demo.py)가 추출 서버를 종료한 다음 판단 서버를 시작했다.
실제 서비스는 모델별 서버 또는 순차 적재 관리가 필요하다.

| 엔드포인트 | 입력 | 동작 |
|---|---|---|
| `POST /w4/extract-evidence` | `w4-evidence-input/0.1` | 추출 factory로 원문 구간 분류 |
| `POST /w4/recommend` | 기존 [W4 계약](w4-contract.md) | 판단 factory로 일반 문항 분석·경험별 판단·코드 정렬 |
| `POST /w4/recommend-from-raw` | `w4-detailed-input/0.1` | 추출 → 선택한 문항 초안의 내용 점검 → 코드 정렬 |

추출 factory를 생략하면 기존 두 엔드포인트 동작은 유지된다. 새 통합 엔드포인트는 명시적인 추출 factory가 없으면 HTTP 503을 반환한다.

## 원문부터 상세 추천까지의 입력

[`samples/detailed/w4_expertise.synthetic.json`](../samples/detailed/w4_expertise.synthetic.json)이 실행 가능한 가상 요청이다.
기존 추출 입력에 `question`, `top_k`를 추가하고 `schema_version`을 바꾼 형태다.

```json
{
  "schema_version": "w4-detailed-input/0.1",
  "request_id": "example",
  "data_kind": "SYNTHETIC",
  "project": {"project_id": "project-demo-sk-hynix", "owner_id": "user-demo"},
  "snapshot": {"snapshot_id": "snapshot-example", "episode_versions": {}},
  "episodes": [],
  "excluded_episode_ids": [],
  "question": {
    "scope_id": "skhynix-2026-march-R260521-IT",
    "question_id": "expertise"
  },
  "top_k": 3
}
```

`episodes`의 각 객체는 `episode_id`, 양의 정수 `version`, `owner_id`, `activity_id`, `title`, `raw_text`다.
클라이언트가 `facts`나 LLM 판단을 넣는 필드는 없다. 서버가 직접 추출하고 원문·ID·버전을 대조한다.
선택할 `question_id`는 `expertise`, `teamwork`, `challenge`, `self_description`, `job_experience`다.
`self_description`은 사용자가 직접 정한 `user_theme`가 필요하며, 없으면 모델을 호출하지 않고 `NEEDS_INPUT`을 반환한다.
현재 실전송이 허용된 주제도 고정 가상 값인 `꾸준히 배우고 적용하는 태도`뿐이다. 임의의 실제 주제를 전송할 수 있다는 뜻은 아니다.
`top_k`는 1~20이다. 5개 문항을 한 요청에 섞지 않고 요청한 한 문항만 평가한다.

## 출력과 검증 범위

`w4-detailed-output/0.1`은 후보의 `status`, `content_checks`, 근거의 정확한 원문·위치, 추가 질문, 순위를 반환한다.
점검 상태는 `SUPPORTED`, `NOT_SHOWN`, `AMBIGUOUS`, `CONTRADICTED`다.
모델 원판정은 `model_status`, 코드가 부족한 근거를 발견해 낮춘 이유는 `validation_issue`에 남는다.
필요한 기간·목표·행동 등의 종류가 없거나 부정·미래 계획·타인 행동을 빌린 근거는 충족으로 올리지 않는다.
종류가 맞다는 것은 필요조건이며 의미·인과관계까지 코드가 증명한다는 뜻은 아니다.

정렬은 문항 전체 상태 → 지원 근거의 종류 수 → 경험 ID다. 내용 점검 10개를 별도 가산점으로 더하지 않는다.
동일한 품질 정렬 조건인 후보는 `tied_on_quality_keys=true`로 표시한다. ID 순서로 갈린 순위는 능력 우열이 아니다.
공식 문구·글자 수·필수 여부는 미확인으로 남고, 길이 제한·지원 자격 판정을 적용하지 않는다.

기존 경로와 동일하게 인증 없음 401, 프로젝트 소유자 불일치 403, JSON 형식 오류 400, 계약 위반 422,
크기 제한 413, LLM 오류 502/503/504를 사용한다. 원문이나 비밀값을 오류 응답에 복사하지 않는다.
사용자 ID는 신뢰할 수 있는 인증 결과여야 한다. **실서비스에서는 DB 조회도 해당 사용자·프로젝트 소유권으로 제한해야 한다.**
현재 입력 목록 필터와 원문 검사만으로 실제 DB의 프로젝트 접근 권한까지 구현했다고 볼 수 없다.

`REAL` 또는 등록하지 않은 가상 내용을 보내면 전송 전에 차단한다. 실제 데이터 허용, 동의·보존 정책,
검색 결과 및 DB 스냅샷 전달은 팀 서비스의 후속 연동 범위다. Graph·Vector Retriever는 아직 목록 입력 방식이다.

## 팀에 필요한 다음 자료

인증 dependency/사용자 ID 규격, 프로젝트·경험 조회 API 또는 저장소 함수, 경험 버전·수정 시점,
검색 후보 형식이 필요하다. 준비되면 입력 어댑터를 작성해 테스트 서버에서 실제 통합 요청을 검증한다.
API 키가 없어서 이번 로컬 추론이 막힌 것은 아니다. 팀 서비스 구현과 운영 품질 승인이 남아 있다.
