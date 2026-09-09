# W4 모델 비교 평가기

현재 상태: 평가 알고리즘과 최고 점수 모델의 호출 연결을 구현하고 로컬 모델 4개의 새 v4 A/B 비교를 완료했다.
정답·가중치는 아직 초안이며 필수 검증 실패로 최종 모델은 선정하지 않았다. [최신 결과·채점 지표의 한계](w4-review-v4-2026-09-09.md)를 참조한다.
경험별 호출·분리 평가 구조는 [v2 안내](w4-evaluation-v2.md), 최신 데이터·설정·실행법은 위 v4 보고서에 있다.
이 문서의 사례 8개·3회 반복과 `epick_w4.evaluate` 내보내기/채점/승인 CLI는 기존 v1 경로다.
v2 수집·채점은 `collect_stage_run()` / `evaluate_stage_runs()` 및 `scripts/run-local-evaluation.py --v2`를 사용한다.
사용자 요청은 **문항 해석과 경험 매칭을 채점하고, 사람이 승인한 정답·가중치만으로 모델을 추천**하는 것이다.
사용 모델은 그 비교의 단독 1위로 선택한다. Solar는 현재 구현된 전송 어댑터이며, 평가 없이 최종 사용 모델로 고정하지 않는다.

검토할 원문과 정답은 [검토 문서](w4-model-evaluation-review.md), 기계가 읽는 기준은
`samples/evaluation/benchmark.draft.json`과 `samples/evaluation/policy.draft.json`에 있다.
가상 사례 8개, 문항:매칭 50:50, 각 요청 3회 반복은 모두 제안이며 승인된 사실이 아니다.

## 무엇을 비교하는가

평가기 `epick_w4/model_eval.py`는 공급자 이름으로 판단하거나 모델에게 심사 점수를 묻지 않는다.
다음 두 과제를 각각 수행한 원시 응답을 승인된 정답과 비교한다.

| 축 | 공통 입력 | 채점 대상 |
|---|---|---|
| 문항 해석 | 문항 원문과 W4 문항 프롬프트 | 기준 ID·문항 인용·필요한 ROLE/ACTION/RESULT·확인 필요 여부 |
| 경험 매칭 | 문항·동일한 승인 기준·동일한 경험 발췌와 W4 매칭 프롬프트 | 관련성·근거 사용 가능 여부와 문제 코드·기준→경험→ACTION 근거 연결 |

매칭 입력에는 사람이 검토한 공통 문항 기준을 준다. 각 모델이 앞 단계에서 만든 기준을 넣지 않는다.
이 방법은 문항 해석 능력과 매칭 능력을 따로 측정한다. 실제 W4 전체 파이프라인의 최종 추천 품질은
별도로 검증해야 한다. 문항 호출이 실패해도 매칭 시험은 동일한 입력으로 수행한다.

정답·가중치·검토 메모는 모델 요청에 포함하지 않는다. 매칭 시험에 주어지는 공통 문항 기준은 해당
시험의 입력이고, 정답인 관련성·근거 판단·연결 목록은 전달하지 않는다.

## 점수와 추천 규칙

정답 한 변형과 판단 전체가 일치하면 사례별 1점, 아니면 0점이다. 사람이 여러 타당한 정답 변형을
등록하면 그중 하나와 일치할 때 1점이다. 단계 내부에 별도 임의 가중치를 넣지 않는다.

```
문항 점수 Q = 100 × 문항 정답 횟수 / 예정된 문항 요청 횟수
매칭 점수 M = 100 × 매칭 정답 횟수 / 예정된 매칭 요청 횟수
종합 점수  = (승인된 문항 가중치 × Q + 승인된 매칭 가중치 × M) / 가중치 합
```

- 축별 사례 가중치는 동일하다. 각 사례의 반복 횟수도 같고 모든 반복을 포함한다.
- 초안은 문항 8개·매칭 7개를 각각 3회 수행하므로 모델당 총 45회 요청이다. 실제 호출 전에 이 양과 비용을 검토한다.
- 지원동기 사례는 문항 과제에만 포함한다. 해당 매칭 과제는 모든 모델에서 동일하게 제외한다.
- 호출 실패·형식 오류는 0점이다. 기록 누락도 분모에 남기며, 미수행 사례가 있는 비교는 추천을 보류한다.
- 승인된 정답이 검증 불가능한 참조, 중복 ID, 원문에 없는 인용을 포함하면 평가 설정 자체를 거부한다.
- 기존 W4 코드가 빠진 ROLE/ACTION/RESULT를 보완해도 모델 점수에는 반영하지 않는다. 보완 전 응답을 채점한다.
- 배열 순서와 알려진 역량 ID의 표시명은 점수에 영향을 주지 않는다. 의미가 없는 `custom_1` 등의 ID는 label도 비교한다.
- 문항 인용의 다른 타당한 범위·새 custom 표현은 사람이 대체 정답으로 등록한다. 자동 유사도 판정이나 임의 동의어 처리는 없다.
- 근거의 누락·추가 목록을 출력한다. 문항 토큰 F1과 매칭 연결 F1은 오류 진단용이며 종합 점수에 포함하지 않는다.
- 진단 F1은 두 집합 모두 비어 있으면 1로 정의한다. 근거 판단·관련성이 틀리면 연결 F1이 1이어도 사례 정답은 0이다.
- 두 개 이상의 서로 다른 모델/설정 후보가 필요하다. 같은 설정을 이름만 바꿔 중복 등록할 수 없다.
- 종합 점수가 같으면 공동 1위다. 모델 이름·제공자·입력 순서로 임의로 하나를 고르지 않는다.
- 전부 0점이면 추천하지 않는다. 최고 관측 점수는 이 세트에서의 상대 비교이며 운영 합격이나 통계적 우월성을 보장하지 않는다.

정답 전체 일치 방식은 엄격하므로 일부 타당한 판단이 낮게 평가될 수 있다. 실제 비교 전 사람이
허용 정답의 범위를 검토해야 한다. 현재 8개는 개발용 공개 초안이다. 일반적인 선정 근거로 쓰려면
모델·프롬프트 조정에 쓰지 않은 독립 사례와 다양한 난이도를 추가해야 한다.

## 사람 승인과 재현 기록

기본 경로에서 실제 또는 가져온 모델 응답은 정답 세트와 정책이 모두 승인돼야 채점할 수 있다.
모의 응답은 계산 검증 목적으로만 초안을 사용할 수 있고 항상 `PREVIEW_ONLY`, 추천 없음으로 출력한다.
모의 답변 파일을 실제 모델 성능의 증거로 사용하지 않는다.

실제 예비 실행에는 `collect_run(..., exploratory=True)`와 `evaluate_runs(..., exploratory=True)`를 사용한다.
이 경로는 초안에 대한 관측값을 계산하지만 `EXPLORATORY_EVALUATION` 사유로 모델 선정을 항상 보류한다.
실제 응답은 `CAPTURED`이며 `SIMULATED`로 바꾸지 않는다. 승인 기록도 자동 생성하지 않는다.
기존 `select_evaluated_client`는 기본 검토 조건을 유지하므로 이 예비 성적으로 모델을 선택할 수 없다.

승인은 검토자·검토 시각·검토한 내용의 SHA-256을 남긴다. 내용이 달라지면 기존 승인은 유효하지 않다.
정책은 정답 세트 해시, 공통 요청/프롬프트 해시, 채점기 버전에 묶인다.
승인자 이름과 `CAPTURED`/`IMPORTED` 구분은 로컬 감사 기록이며 본인 인증이나 전자서명은 아니다.
실제 사람이 승인한 뒤에만 아래 명령을 실행한다.

저장소 루트에서, 아래 `python`은 해당 PC의 Python 실행 파일로 대체할 수 있다.

```powershell
python -m epick_w4.evaluate approve --input samples/evaluation/benchmark.draft.json --reviewer "실제 검토자" --output samples/evaluation/benchmark.approved.json
python -m epick_w4.evaluate approve --input samples/evaluation/policy.draft.json --benchmark samples/evaluation/benchmark.approved.json --reviewer "실제 검토자" --output samples/evaluation/policy.approved.json
```

정답·사례·프롬프트를 수정했다면 검토 후 정책의 `benchmark_sha256`과 `protocol_sha256`도 갱신해야 한다.
계산 함수는 각각 `document_digest(benchmark)`, `digest(build_requests(benchmark))`다.
가중치만 수정했다면 정책만 다시 승인한다. 승인 전 기록은 유지하고 새 출력 경로를 사용한다.

## 모델 응답 모으기

CLI 자체는 네트워크를 호출하지 않는다. 공통 요청을 JSON으로 내보내 외부 실행기의 원시 응답을
가져오거나, 기존 `JsonClient.complete_json` 어댑터를 Python에서 주입한다.

```powershell
python -m epick_w4.evaluate export --benchmark samples/evaluation/benchmark.approved.json --policy samples/evaluation/policy.approved.json --output output/evaluation-requests.json
```

```python
from epick_w4.model_eval import collect_run

# benchmark, policy: 승인된 JSON 객체
# client: 호출자가 선택·설정한 JsonClient. 실제 호출은 simulated=False.
run = collect_run(
    benchmark, policy, client,
    candidate_id="실제로 평가하는 모델 및 설정의 식별자",
    generation_config={"temperature": 0, "max_tokens": 6000},  # 예시: 실제 적용 설정을 기록
)
```

평가 결과를 사용한 호출 모델 선택은 아래의 `select_evaluated_client`로 연결한다.
로컬 llama.cpp용 `LocalClient`와 실제 가상 샘플 비교 실행기를 추가했다. 상용 API 키 발급과 실제 개인정보 전송은 수행하지 않았다.
공통 전송 허용 목록에는 고정된 가상 평가 요청과, 기존 가상 원문에서 만들 수 있는 추출 Fact만 추가했다.
임의 문항·경험을 SYNTHETIC으로 표시해 보내는 것은 계속 차단한다.
실제 실행에는 선택한 모델의 어댑터와 키가 필요하고, 실행 비용이 발생할 수 있다.

`collect_run`은 사례·반복별 공통 입력 해시, 원시 응답/실패, 모델·공급자·실행 설정을 기록한다.
자동 재시도는 하지 않는다. 오류가 발생해도 다음 예정 요청은 계속 수행한다.
`generation_config`에는 실제 생성 설정만 넣는다. 자격증명은 어댑터에서 별도로 관리한다.

외부 실행기에서 가져오는 파일은 `schema_version=w4-model-run/0.1`, `provenance=IMPORTED`로 기록한다.
`export`의 두 해시와 반복 횟수를 그대로 넣고, 각 응답에 다음 형식을 사용한다.

```json
{
  "case_id": "paraphrase",
  "axis": "question",
  "repeat": 0,
  "request_sha256": "해당 export request 객체를 digest()한 값",
  "response": {"criteria": [], "required_facts": [], "needs_confirmation": true},
  "error": null
}
```

응답의 `axis`는 question/matching, 호출 `stage`는 question/candidates다.
실패한 요청도 `response=null`, `error="TIMEOUT"` 등으로 기록한다. 실패를 삭제해서는 안 된다.
응답 묶음에는 candidate_id, provider, model, generation_config, created_at, records도 필요하다.
가져온 파일의 원본·설정·실패 포함 여부를 사람이 확인하고 같은 `approve` 명령으로 검토 기록을
추가한다. 검토되지 않은 가져온 파일은 추천의 근거로 채택하지 않는다.

## 점수 보고서

```powershell
python -m epick_w4.evaluate score --benchmark samples/evaluation/benchmark.approved.json --policy samples/evaluation/policy.approved.json --run output/model-a-reviewed.json --run output/model-b-reviewed.json --output output/evaluation-report.json --markdown output/evaluation-report.md
```

모델별 두 축 점수·종합 점수·공동 순위와, 사례별 정오답·누락/추가 판단을 출력한다.
해시가 다른 입력·프롬프트, 다른 반복 횟수, 중복 사례를 섞으면 평가를 거부한다.
설정값 차이는 보고서에 표시되므로 어떤 모델/설정을 비교했는지 확인할 수 있다.

외부 호출 없는 계산 시연:

```powershell
python scripts/demo-model-evaluation.py --output-dir output/evaluation-demo
python -m unittest discover -s tests -p test_model_eval.py -v
```

시연은 정답 복사와 의도적인 누락을 가진 두 fixture를 사용한다. 특정 실제 모델을 나타내지 않는다.
모든 CLI 출력은 기존 파일을 덮어쓰지 않는다.

## 최고 점수 모델을 실제 호출에 연결

흐름은 **공통 평가 → 승인한 기준으로 채점 → 단독 1위 모델·설정 선택 → 이후 W4 요청에 사용**이다.
모델 비교를 별도로 실행하고 응답 기록을 보존한다. 사용자 요청마다 모든 모델을 다시 호출해 경쟁시키는 방식이 아니다.

구현은 [model_selection.py](../epick_w4/model_selection.py)의 `select_evaluated_client`다.
저장된 점수 요약만 읽는 대신, 정답·정책·원시 응답 기록을 기존 평가기로 다시 채점해 선정 근거를 확인한다.
이 재채점은 로컬 계산이며 모델을 호출하지 않는다.

```python
from epick_w4 import recommend, select_evaluated_client
from epick_w4.api import create_router

# 호스트 백엔드가 검토된 benchmark, policy, runs와 호출 어댑터를 준비한다.
# candidate_id -> 인자 없는 생성 함수. 키·엔드포인트는 호스트에서 관리한다.
# 각 어댑터는 provider, model, simulated=False, generation_config와
# complete_json(stage=..., system_prompt=..., payload=...)를 제공한다.
client_factories = {
    "실제-평가-후보-A": create_candidate_a_client,
    "실제-평가-후보-B": create_candidate_b_client,
}

def make_selected_client():
    return select_evaluated_client(
        benchmark, policy, runs, client_factories=client_factories,
    )

result = recommend(payload, user_id=authenticated_user_id, llm=make_selected_client())
# HTTP 호스트에서는 동일한 팩터리를 주입한다.
router = create_router(authenticate=authenticate, client_factory=make_selected_client)
```

위 이름들은 호스트 연결 예시다. 실제 후보 모델·키나 없는 API를 자동으로 생성하지 않는다.
**선정된 후보의 팩터리만 실행**하므로 탈락한 모델의 키를 읽거나 요청을 보내지 않는다.
정답·정책 미승인, 모의 성적, 기록 누락, 단일 후보, 전부 0점이면 호출 모델을 선택하지 않는다.
동점이면 `LLM_SELECTION_TIED`를 반환한다. 임의로 이름순·가격순으로 고르거나 Solar로 전환하지 않는다.

선정된 모델의 어댑터가 없으면 `LLM_SELECTED_ADAPTER_UNAVAILABLE`을 반환한다. 낮은 점수의 연결 가능한 모델을
1위로 바꿔 부르지 않는다. 어댑터가 보고한 공급자·모델·생성 설정이 평가 당시와 다르거나 모의 클라이언트이면
`LLM_SELECTED_CONFIGURATION_MISMATCH`로 거부한다. 호출 중 설정이 바뀌어도 다음 모델 요청 전에 확인한다.
평가할 때 `generation_config`에는 실제 생성 설정 전체를 기록해야 한다. `SolarClient.generation_config`는
현재 적용하는 temperature·reasoning_effort·max_tokens·stream을 제공한다. 어댑터가 설정을 정직하게 보고하는지와
실제로 해당 설정을 전송하는지는 호스트의 책임이며 공급자 내부 동작을 독립 검증하는 기능은 아니다.

선택 결과는 추천·추출 응답의 `inference.model_selection`에 남는다. 후보 ID, 축별 점수·종합 점수,
정답·정책·프롬프트·응답 기록·설정의 해시를 확인할 수 있다. 평가 정답이나 키를 모델 입력에 추가하지 않는다.
공급자와 관계없이 기존의 허용된 가상 데이터만 전송하며 `REAL` 데이터 차단도 유지한다.

현재 평가의 두 축은 **문항 해석과 경험 매칭**이다. 선택한 모델을 원문 추출에도 사용할 수 있지만,
그 점수로 원문 추출 정확도까지 입증된 것은 아니다. 메타데이터에 `unevaluated_stages=["extraction"]`을 남긴다.
추출 정답 사례·지표와 별도 실제 비교는 추가했지만, 이 선택 함수의 점수에는 합산하지 않는다.
추출까지 포함한 최종 선정에는 사람의 기준 검토와 단계별 모델을 연결한 실행 검증이 남아 있다.
현재 두 축의 50:50 제안을 임의로 바꾸거나 추출 점수를 새로 만들어 합산하지 않았다.

실제 평가 자료와 해당 어댑터를 준비한 후 CLI에서도 선택 경로를 사용할 수 있다.
아래 `approved`/모델 응답 파일들은 준비해야 할 경로 예시이며 현재 저장소에 승인된 실제 성적은 없다.

```powershell
python -m epick_w4 --engine evaluated --input samples/w4_semantic.json --user-id user-demo --benchmark samples/evaluation/benchmark.approved.json --policy samples/evaluation/policy.approved.json --run output/model-a-reviewed.json --run output/model-b-reviewed.json --output output/recommendation-evaluated.json
```

원문 추출은 같은 명령에 `--operation extract`와 추출용 입력 JSON을 지정한다. 기존 `--engine solar`는
Solar 단독 통신 점검용으로 유지한다. 이 옵션을 사용한 결과가 모델 비교의 우승을 뜻하지 않는다.
현재 CLI에 내장된 실제 전송 어댑터는 Solar뿐이다. 다른 공급자가 1위면 해당 어댑터를 연결해야 한다.
Python/백엔드는 `client_factories`로 다른 공급자를 등록할 수 있고, CLI의 Python 진입점
`main(argv, client_factories=...)`도 같은 등록을 받는다. `W4_LLM_MODEL`로 평가의 우승 모델을 덮어쓰지 않는다.

선택 기능의 테스트 17개를 추가했다. 모의 비교 자료와 Solar 외 모의 어댑터로 최고점 선택,
초기 선택 연결 당시 동점·미평가·설정 불일치·어댑터 부재 처리, CLI와 HTTP·추출 연결을 확인해 **164개 테스트를 통과**했다.
현재 v3 오류 회귀 검증까지 포함한 전체 테스트는 **197개 통과**다.
테스트 안의 가짜 승인·응답 기록은 실제 성적 파일로 저장하지 않았다. 실제 최고점 모델은 아직 정해지지 않았다.

## 초기 구현의 검증 기록 — 실제 모델 실행 전

2026-09-08, Python 3.12.14와 `uv.lock`으로 만든 노트북 전용 별도 테스트 환경에서
평가기 31개와 기존 82개를 합친 **113개 테스트가 모두 통과**했다. API 테스트도 포함한다.
동기화된 기존 `.venv`는 다른 PC의 Python 경로를 가리켜 이 검증에는 사용하지 않았다.

CLI의 요청 내보내기·모의 응답 채점·JSON/Markdown 보고서 생성을 실제 실행했다.
라이브러리와 CLI 보고서는 동일했다. 정답을 복사한 fixture는 100점, 문항 요구와 근거 연결을
의도적으로 한 사례씩 누락한 fixture는 86.607143점이었다. 이는 계산 검증값이며 LLM 성능 점수가 아니다.
보고서는 `PREVIEW_ONLY`, 추천은 `WITHHELD`로 표시됐다.

`git diff --check`와 새 파일 공백 검사를 통과했고, 새 Python 파일 4개는 Python 3.10 문법으로
파싱했다. Python 3.10 런타임에서 실행한 검증은 아니다. 실제 모델 API 호출은 수행하지 않았다.

## 방법의 근거와 이 프로젝트의 선택

- 같은 시나리오와 지표로 모델을 비교하는 접근은 [HELM 논문](https://arxiv.org/abs/2211.09110)을 참고했다.
- 주 지표의 정확 일치 개념은 [scikit-learn의 subset accuracy 정의](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.accuracy_score.html)에 근거한다. 구조화된 W4 판단을 비교하는 적용 방식은 이 프로젝트의 검토 대상 제안이다.
- 진단 F1의 정밀도·재현율 계산은 [scikit-learn 공식 정의](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.precision_recall_fscore_support.html)를 따른다. 두 집합이 모두 비었을 때 1을 쓰는 것은 명시한 로컬 규칙이다.

문항 50:매칭 50, 3회 반복, 8개 초안 사례와 정답의 타당성을 위 자료가 보장하지 않는다.
이 값과 정답은 사람의 검토·승인 대상이다. scikit-learn을 실행 의존성으로 추가하지 않았으며
계산은 Python 표준 라이브러리로 수행한다.
