# W4 3단계: 경험 원문에서 근거 추출

기록일: 2026-09-08. 개발용 계약 `0.1`. 구현은 [evidence_extraction.py](../epick_w4/evidence_extraction.py)다.

현재는 Qwen3.5-9B·Qwen3-14B·Gemma 4 12B·Gemma 4 26B A4B의 실제 추출을 별도로 평가했다.
2026-09-09 v4 보완 설정 B의 새 6개 경험·30구간에서 전체 일치율은 각각 43.33%, 70.00%, 83.33%, 73.33%다.
추출 필수 검사는 Gemma 두 모델이 통과했지만 정답은 사람 미검토 초안이며 운영 모델 선정은 보류했다.
[최신 결과·두 모델 조합·실행법](w4-review-v4-2026-09-09.md)을 참조한다. 12경험·53구간의 이전 측정은 [v3 기록](w4-review-v3-2026-09-09.md)에 보존했다.
이전 Qwen3-4B·Granite Micro 결과는 [v1 기록](w4-local-evaluation-2026-09-08.md)에 있다. 아래 모의 실행과 구분한다.

경험 원문과 소유자·버전을 받아 **역할·행동·결과·목표·기간·난관·소회·상황**을 원문 위치에 연결한다.
LLM은 주어진 원문 구간의 종류와 주체·서술 상태를 분류한다. 코드가 구간 ID를 검사하고 발췌문과 위치를 원문에서 복사한다.
추출되지 않은 항목에는 후속 질문을 남긴다. 문항 적합성이나 추천 순위는 이 단계에서 판단하지 않는다.

## 실행과 확인한 결과

저장소 폴더에서 키 없이 모의 응답으로 실행한다. 기존 출력 파일은 덮어쓰지 않으므로 재실행 시 새 이름을 지정한다.

```powershell
python scripts/demo-evidence-extraction.py --output output/evidence-extraction-demo.json
```

입력은 [가상 원문 4개](../samples/extraction/raw-experiences.synthetic.json), 분류는 [미리 작성한 모의 응답](../samples/extraction/model-output.mock.json)이다.
학습·API 협업·팀 성과 사례의 원문은 기존 가상 샘플을 재사용했다. 목표·기간 등의 표현을 점검하려고 별도의 가상 도서관 예약 사례를 추가했다.
모든 사람·활동·성과 수치는 개발용 허구다. 기존 학습·협업 원문에 부족한 내용을 덧붙이지 않았다.

| 가상 경험 | 모의 응답을 처리한 결과 |
|---|---|
| 학습·적용 | 역할·행동·결과 3개. 학습 기간은 `NOT_EXTRACTED`이며 확인 질문을 반환 |
| API 협업·오류 개선 | 역할 1개·행동 2개·결과 1개. 공동 목표와 기간 등은 미추출 |
| 팀 성과만 기록 | 팀 결과 1개만 Fact에 포함. 팀 역할·행동은 본인 근거로 사용하지 않고 `REVIEW_REQUIRED` |
| 도서관 예약 도구 | 역할 1개·행동 2개·결과 1개. 목표·기간·난관·소회·상황은 별도 원문 구간으로 보존. 미래 계획은 완료한 행동에서 제외 |

합계는 원문 구간 19개, 기존 Fact 형식으로 넘길 근거 12개다. 결과의 `inference.mode=SIMULATED_LLM`과
`validation_status=REQUIRES_CANDIDATE_VALIDATION`을 확인한다. **실제 LLM을 실행하거나 추출 정확도를 측정한 결과가 아니다.**

## 입력 계약

```python
from epick_w4 import extract_evidence

result = extract_evidence(payload, user_id=authenticated_user_id, llm=client)
```

| 필드 | 조건 |
|---|---|
| `schema_version` | `w4-evidence-input/0.1` |
| `request_id` | 비어 있지 않은 요청 ID |
| `data_kind` | 현재 `SYNTHETIC`만 실행. `REAL`은 모의 클라이언트에서도 차단 |
| `project` | `project_id`, `owner_id`. 소유자가 호출자가 주입한 인증 사용자와 같아야 함 |
| `snapshot` | `snapshot_id`, `episode_versions`의 경험 ID→양의 정수 버전 |
| `episodes` | 각 항목은 `episode_id`, `version`, `owner_id`, `activity_id`, `title`, `raw_text` |
| `excluded_episode_ids` | 선택 필드, 기본 빈 목록 |

추출 입력에는 미리 작성한 `facts`나 회사·문항 조건을 넣지 않는다. 계약에 없는 필드는 거부한다.
공식 지원서 문구·글자 수·필수 여부의 미확인 상태는 유지하며, 원문을 자르거나 경험을 제외하는 조건으로 사용하지 않는다.

타 사용자 경험과 제외 경험은 모델 입력·반환 결과에서 빠진다. Snapshot 버전이 맞지 않는 경험도 빠지고,
`EPISODE_VERSION_MISMATCH` 진단을 반환한다. 진단에 제외된 원문이나 경험 ID를 노출하지 않는다.
백엔드는 DB의 실제 소유권과 Snapshot을 확인해 입력을 구성해야 한다. 본문에 소유자 ID를 적는 것만으로 실제 소유권을 증명할 수 없다.

## 원문 구간과 모델 응답

코드는 비어 있지 않은 줄마다 `u1`, `u2` 등의 ID를 붙인다. 한 줄 내부의 공백·문장·수치는 그대로 보존한다.
줄바꿈 없는 문단은 하나의 구간이다. 모델이 부정 표현을 잘라낸 일부 문장만 근거로 선택하게 하지 않기 위한 초기 방식이다.
한 구간에 서로 다른 주체·완료 상태가 섞여 있으면 `MIXED`와 `INSUFFICIENT_CONTEXT`로 검토를 요청해야 한다.
세밀한 문장 분할이나 날짜·수치의 정규화는 아직 구현하지 않았다.

외부 모델에는 한 경험의 `episode_id`, `episode_version`, `source_units[{unit_id,text}]`만 전달한다.
제목·인증 ID·기업정보·문항은 전송하지 않는다. 같은 경험의 앞뒤 구간을 함께 읽도록 프롬프트에 지정한다.

모델 출력은 아래 구조만 허용한다. 모든 입력 구간을 정확히 한 번씩 반환해야 한다.

```json
{
  "units": [
    {"unit_id": "u1", "kinds": ["ACTION"], "subject": "SELF", "assertion": "AFFIRMED", "issue": null}
  ]
}
```

| 분류 | 허용 값 |
|---|---|
| `kinds` | `ROLE`, `ACTION`, `RESULT`, `GOAL`, `PERIOD`, `OBSTACLE`, `REFLECTION`, `CONTEXT`. 중복 없이 여러 종류 가능 |
| `subject` | `SELF`, `TEAM`, `OTHER`, `UNSPECIFIED`, `MIXED` |
| `assertion` | `AFFIRMED`, `NEGATED`, `PLANNED`, `HYPOTHETICAL`, `UNCERTAIN`, `MIXED` |
| `issue` | `null`, `INSUFFICIENT_CONTEXT`, `INSTRUCTION_IN_SOURCE`, `NO_EVIDENCE` |

`AFFIRMED`는 원문이 그렇게 서술한다는 뜻이다. 현실의 사실이나 인과관계가 검증됐다는 뜻이 아니다.
종류가 없으면 사유가 있어야 하며, 지시문·근거 없음으로 분류한 구간의 `kinds`는 비워야 한다.
주체가 `MIXED`이거나 서술 상태가 `UNCERTAIN`/`MIXED`이면 `INSUFFICIENT_CONTEXT`가 필요하다.
존재하지 않는 ID, 누락·중복, 허용되지 않은 값, 모델이 덧붙인 발췌문·위치·순위 등은 오류로 처리한다.

## 출력 계약과 다음 단계 전달

출력은 `schema_version=w4-evidence-output/0.1`이며 `episodes`의 각 항목이 다음 정보를 가진다.

| 필드 | 의미 |
|---|---|
| `episode` | 원문·메타데이터와 기존 추천 입력 형식의 `facts` |
| `evidence_units` | 모든 원문 구간, 코드가 만든 ID·발췌·위치, 모델 분류·문제 표시 |
| `field_coverage` | 8종류별 상태, 사용 가능한 `evidence_ids`, 검토할 `review_evidence_ids` |
| `follow_up_questions` | 추출 근거가 없는 종류별 확인 질문. 원문 부족과 모호함을 구분 |
| `validation_status` | 항상 `REQUIRES_CANDIDATE_VALIDATION` |

원문 위치는 Python Unicode 코드 포인트의 시작 포함·끝 제외 범위다. 각 발췌는
`raw_text[start:end] == text`이며 경험 ID·버전과 함께 저장한다. JavaScript UTF-16 인덱스와는 다르다.
원문·줄바꿈을 편집하면 경험 버전을 올리고 다시 추출해야 한다.

문제 표시가 없고 `AFFIRMED`인 구간 중 ROLE/ACTION은 `SELF`인 경우만 `episode.facts`에 넣는다.
RESULT는 `SELF`/`TEAM`/`UNSPECIFIED`를 허용하되 원문 그대로 유지한다. 팀 성과를 개인 단독 성과로 바꾸지 않는다.
목표·기간 등은 `evidence_units`에 남겨 기존 ROLE/ACTION/RESULT에 억지로 넣지 않는다.
서로 다른 종류에 같은 구간이 연결돼도 독립된 증거 여러 개가 생긴 것은 아니다.

`EXTRACTED`는 해당 종류의 사용할 수 있는 추출 구간이 있다는 뜻이고, `REVIEW_REQUIRED`는 관련 구간이 있으나
주체·서술 상태 등의 검토가 필요하다는 뜻이다. `NOT_EXTRACTED`는 추출되지 않았다는 뜻이며 미경험을 입증하지 않는다.
사용 가능한 구간과 검토 구간이 함께 있으면 두 ID 목록을 함께 읽는다. 후속 질문은 문항과 관련된 것을 선택할 재료이며,
8종류 모두를 모든 자기소개서 문항의 필수조건으로 요구하지 않는다.

전체 `status`는 후보가 없으면 `NO_ELIGIBLE_EPISODES`, 누락·검토 항목 등이 있으면 `EXTRACTED_WITH_LIMITATIONS`,
그 밖에는 `EXTRACTED`다. 어떤 상태도 문항 충족, 지원 자격 또는 추천 확정을 뜻하지 않는다.
`inference`에는 모드·공급자·모델·프롬프트 버전과 SHA-256, 경험별 호출 입력 SHA-256을 남긴다.
해시는 키 정렬·공백 제거·Unicode 유지 방식으로 직렬화한 JSON의 SHA-256이며 프롬프트도 JSON 문자열로 계산한다.

`episode`는 기존 추천 입력의 `episodes`로 옮길 수 있고, 단위 테스트에서 계약 파싱과 규칙 검증 경로를 확인했다.
실제 통합에서는 원문·소유권·버전을 다시 검사하고, 문항·기업정보와 연결해 4단계 판단을 수행해야 한다.
`scripts/run-local-evaluation.py`가 **허용된 가상 원문의 추출 결과부터 최종 LLM 추천까지 연결**한다.
고정된 가상 원문에서 파생된 Fact만 추천 입력으로 허용하며, 임의의 실제 원문 전송은 계속 차단한다.
목표·기간 등과 [문항별 내용 기준](w4-question-criteria.md)을 연결하는 기능도 다음 단계다.

## 평가 모델 선택과 HTTP 연결

호출 모델은 공통 평가에서 최고 점수를 기록한 모델을 선택한다. [모델 평가·선택 연결](w4-model-evaluation.md#최고-점수-모델을-실제-호출에-연결)의
`select_evaluated_client`가 반환한 클라이언트를 추출기에 주입한다. Solar를 고정하는 구조가 아니다.
실제 평가 자료와 해당 모델의 어댑터·키를 준비한 뒤 아래처럼 선택한다. 파일 이름은 준비할 경로 예시다.
이 명령은 외부 모델에 허용된 가상 원문을 전송하며 API 비용이 발생한다. 이번 검증에서는 실행하지 않았다.

```powershell
python -m epick_w4 --operation extract --engine evaluated --input samples/extraction/raw-experiences.synthetic.json --user-id user-demo --benchmark samples/evaluation/benchmark.approved.json --policy samples/evaluation/policy.approved.json --run output/model-a-reviewed.json --run output/model-b-reviewed.json --output output/evidence-extraction-evaluated.json
```

이 선택 함수가 사용하는 평가 축은 문항 해석·경험 매칭이며 추출 점수까지 선택에 반영하지는 않는다.
응답의 `inference.model_selection.unevaluated_stages`는 이 선택 계약의 범위를 나타낸다.
추출 성능 자체는 `extraction_eval.py`로 별도 측정했고, 추출 후보의 자동 선정·혼합 호출 검증은 남아 있다.
기본 CLI에 내장된 전송 어댑터는 Solar이며, 실제 로컬 실행기는 `LocalClient`를 직접 주입한다.
다른 공급자가 1위면 해당 어댑터를 등록해야 하며 Solar로 자동 대체하지 않는다.
Solar 단독 통신 점검에는 기존 `--engine solar`를 사용할 수 있다. 키 설정은 [LLM 연결 안내](w4-llm.md)를 참조한다.
평가 기반 `make_selected_client`를 `create_router(authenticate=..., client_factory=make_selected_client)`에 주입한 FastAPI 앱은
`POST /w4/extract-evidence`로 추출 입력을 받는다. 기존 `POST /w4/recommend`도 유지한다.
이 저장소가 인증 서버나 실제 백엔드·DB를 제공하는 것은 아니다.

현재 전송은 [추출 전용 허용 목록](../epick_w4/extraction_allowlist.json)에 등록된 가상 원문 12개의 내용만 허용한다.
`SYNTHETIC` 표시만 바꾸거나 원문·ID·버전·프롬프트에 임의 내용을 덧붙이면 통과하지 못한다.
기존 추천용 허용 목록은 별도로 유지한다. 모의 클라이언트는 외부 통신 없이 경계 조건 테스트에 사용한다.

인증 범위와 모든 대상의 입력 제한·허용 목록 검사를 **첫 호출 전**에 수행한다. 경험당 한 번, 요청당 최대 20번을 순차 호출한다.
현재 구현 한도는 경험당 원문 12,000자, 구간 64개, 구간당 3,000자, 요청 전체 원문 50,000자다.
이는 개발용 처리 한도이며 회사 지원서 글자 수와 무관하다. 초과하면 오류를 반환하고 자동 절단·재시도하지 않는다.
중간에 모델 호출 또는 응답 검증이 실패하면 성공 응답을 반환하지 않는다. 앞서 완료한 외부 호출 비용까지 취소되지는 않는다.

## 검증과 코드 검토

추출 테스트 28개와 HTTP 추출 테스트 6개를 추가했다. API 의존성이 있는 로컬 환경에서 기존 테스트를 포함한
**147개가 통과**했다. 전부 가상 데이터·모의 모델 응답·모의 HTTP를 사용했다.

원문 위치와 이모지·CRLF·동일 문장 반복, 응답 순서 변경, 주체·부정·계획·혼합 분류의 처리,
ID 변조·누락·중복·추가 필드 거부, 인증·제외·버전 필터, 입력 제한과 호출 전 전송 차단을 검사했다.
검토 과정에서 HTTP 파서를 거치지 않는 Python 호출의 메타데이터도 잘못된 Unicode를 거부하도록 보완했다.
경험별 판단·분리 평가·v3 오류 회귀 검증까지 포함한 현재 전체 테스트는 197개다. 실제 로컬 분류 정확도도 예비 측정했고 오류를 기록했다.
지시문 탐지의 안정성, 활동 간 충돌이나 성과 인과관계의 종합 품질이 입증된 상태는 아니다.
모델 평가기의 정답·가중치는 초안이며 사람 검토가 남아 있다. 추출 점수는 문항·매칭 점수와 합산하지 않는다.
