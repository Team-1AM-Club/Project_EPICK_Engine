# W4 LLM 및 API 연결

상태: **호출 코드·API 연결부와 실제 로컬 모델 호출 구현. 상용 API의 실제 호출은 미검증**.
사용 모델은 [공통 평가의 최고 점수로 선택](w4-model-evaluation.md#최고-점수-모델을-실제-호출에-연결)한다.
이 문서는 현재 구현된 Solar 전송 어댑터의 개별 통신 점검 안내이며, Solar를 최종 모델로 확정한 문서가 아니다.
Upstage 키가 아직 발급되지 않아 Solar 전송 어댑터 검증은 모의 응답으로 진행했다.
실제 로컬 모델의 최신 A/B 비교와 두 모델 조합·상세 문항 시연은 [v4 검토 보고서](w4-review-v4-2026-09-09.md)에 있다.
기존 `output/collaboration.json`, `learning.json`, `diagnostic.json`은 규칙 모드 결과다.
후속 추가한 원문 근거 추출 API와 별도 가상 샘플·전송 허용 범위는 [추출 계약과 실행법](w4-evidence-extraction.md)을 참조한다.

## Solar 개별 통신 점검

기본 모드는 `rules`다. 아래의 Solar 개별 통신 점검은 `solar`를 명시한다. 평가 결과로 선택할 때는 `evaluated`를 사용한다.
팀 백엔드가 없어도 로컬 가상 JSON으로 모델 API를 호출할 수 있다.
키를 발급받은 뒤 아래 명령을 **로컬 PowerShell**에서 실행한다.

```powershell
$w4Key = Read-Host 'Upstage API key' -AsSecureString
$env:UPSTAGE_API_KEY = [System.Net.NetworkCredential]::new('', $w4Key).Password
$w4Key.Dispose()
Remove-Variable w4Key

powershell.exe -NoProfile -File .\scripts\run-demo.ps1 -Scenario semantic -Engine solar
```

키 값은 입력 화면이나 명령 이력에 표시되지 않는다. 해당 PowerShell 세션과 자식 프로세스에만
설정되며, 노트북에서는 별도로 설정한다. `.env` 파일은 자동으로 읽지 않는다.
키를 JSON 본문·채팅·Git에 넣지 않는다. 환경변수가 이미 설정되어 있으면 실행 명령만 사용한다.

결과는 `output/semantic-solar-시간.json`에 저장한다. 기존 파일은 덮어쓰지 않는다.
`LLM_API_KEY_MISSING`은 키가 전달되지 않았다는 뜻이다. 실패 후 규칙 결과로 자동 대체하지 않는다.
Solar 통신은 Python 표준 라이브러리만으로 실행한다.

```shell
python -m epick_w4 --input samples/w4_semantic.json --user-id user-demo --engine solar
```

## API로 받기

파일과 무관하게 같은 JSON 객체를 전달할 수 있다.

```python
from epick_w4 import recommend
from epick_w4.solar_client import SolarClient

result = recommend(payload, user_id=authenticated_user_id, llm=SolarClient.from_env())
```

FastAPI 백엔드에는 제공된 라우터를 등록한다. `my_backend.auth`는 팀의 실제 인증 모듈로 교체한다.

```python
from fastapi import FastAPI
from epick_w4.api import create_router
from epick_w4.solar_client import SolarClient
from my_backend.auth import authenticated_user_id

app = FastAPI()
app.include_router(create_router(
    authenticate=authenticated_user_id,
    client_factory=SolarClient.from_env,
))
```

`POST /w4/recommend`, `Content-Type: application/json`에 `samples/w4_semantic.json`과 같은
본문을 보내면 추천 JSON을 반환한다. 인증 함수는 신뢰된 사용자 ID 문자열을 반환하거나 인증 오류를
발생시켜야 한다. 임의 요청 헤더나 본문을 인증으로 쓰면 안 된다. 실제 DB 프로젝트 접근 권한과
경험 소유권·Snapshot 확인은 백엔드에서 수행해야 한다. 이 저장소는 연결부를 제공하며 상시 서버를
실행하지 않는다. 경로와 계약은 팀 합의 전의 내부 초안이다.

선택 의존성 설치와 전체 테스트:

```powershell
uv sync --locked --extra api --extra test
powershell.exe -NoProfile -File .\scripts\run-demo.ps1 -Scenario tests
```

`uv` 대신 사용 중인 Python에 `python -m pip install -e ".[api,test]"`로 설치할 수도 있다.
각 PC에서 가상환경을 따로 생성한다. 스크립트는 프로젝트 `.venv`를 우선 사용한다.

## 전송 범위

`SYNTHETIC` 입력만 허용하며, 아래 샘플의 실제 내용 해시도 대조한다.

- `samples/w4_collaboration.json`
- `samples/w4_learning.json`
- `samples/w4_semantic.json`

`epick_w4/synthetic_allowlist.json`에 문항과 경험 ID·버전·제목·fact 내용 해시가 있다.
실제 데이터를 가상으로 잘못 표시하거나 내용을 수정하면 `LLM_SYNTHETIC_SAMPLE_REQUIRED`로
중단한다. 첫 모델 호출 전에 전체 후보를 검사하고 각 HTTP 전송 직전에도 검사한다.
새 가상 샘플은 내용을 검토하고 허용 목록도 갱신해야 한다. 샘플 파일 편집만으로 전송 범위가 늘어나지 않는다.
`REAL`은 `LLM_REAL_DATA_NOT_ENABLED`로 차단한다. API에서도 같은 제한을 적용한다.

모델에 보내는 것은 문항, 검사한 문항 기준, 경험 ID·버전·제목과 허용된 ROLE/ACTION/RESULT 발췌다.
전체 경험 원문, 사용자·프로젝트 ID, 회사 Claim, 원본 수집 묶음은 모델 메시지에 넣지 않는다.
회사 Claim의 상태·근거·범위 검사는 기존 W3 전달 계약을 따른다.

## 판단과 검증

정상 추천은 문항 분석 1회와 경험별 판단 N회다. 원문 추출부터 실행하면 경험별 추출 N회가 더해진다.

1. `question`: 기준 ID·이름·정확한 문항 인용과 필요한 ROLE/ACTION/RESULT를 구조화한다.
2. `candidates`: 문항 기준과 경험 하나를 전송한다. fact의 본인 기여·부정·문맥을 판단하고 기준과 ACTION fact ID를 연결한다.

`JsonClient.complete_json(stage=..., system_prompt=..., payload=...)` 계약으로 호출부를 교체할 수 있다.
어댑터를 주입하지 않으면 규칙 모드다. 현재 개발 프롬프트 버전은 `w4-semantic-grounding/0.3`다.
출력 형식·원문 인용·문맥·문항 의미·근거 추출을 분리한 현재 평가는 [v4 안내](w4-review-v4-2026-09-09.md)를 참조한다.
기존 모델을 호출하는 추론이며 모델을 새로 학습시키지 않는다.

소유권·제외·Snapshot 버전·원문 위치·인용 일치를 먼저 검사한다. 모델 응답에는 모든 경험과 fact가
누락·중복 없이 있어야 하며, 같은 경험의 허용된 ACTION fact만 기준에 연결할 수 있다.
문항 인용도 실제 연속 원문이어야 한다. 임의 상태·순위·점수 같은 추가 필드는 거부한다.

최종 상태와 순위는 코드가 결정한다. 상태 → 문항 기준 충족 개수 → 근거 종류 → 기업 연결 기준 개수 →
경험 ID 순서다. 이유는 선택된 원문과 기준으로 조립한다. 기업 맥락 연결은 기존 규칙이며
전체 지원 자격은 `NOT_ASSESSED`다. 참조와 원문이 맞아도 의미 판단이 정확하다는 보장은 없다.

`inference`에는 모드·모델·공급자·프롬프트 버전·호출 단계와 입력/프롬프트 해시가 남는다.
`SIMULATED_LLM`은 미리 작성한 응답이며 `LLM`은 실제 클라이언트를 선택한 실행이다.
`calls=[]`는 필요한 입력이 없어 모델 호출 전에 중단한 경우다. 키·원문 전문·내부 사고 과정·
공급자 오류 본문을 이 메타데이터에 저장하지 않는다.

## 통신 설정과 제한

공식 Quickstart의 `https://api.upstage.ai/v1/chat/completions`와 기본 모델 `solar-pro4`를 사용한다.
모델 변경은 서버의 `W4_LLM_MODEL` 환경변수에서만 받는다. `temperature=0`, `reasoning_effort=none`,
`max_tokens=6000`, 비스트리밍이다. 프롬프트에 JSON 형태를 명시하고 로컬에서 엄격하게 검사한다.

문항 4,000자, 후보 20개, 경험당 fact 64개, 프롬프트와 입력 JSON 합계 50,000자,
HTTP 요청 250,000바이트, 응답 1,000,000바이트로 제한한다. 초과하면 조용히 자르지 않고 중단한다.
현재 허용된 샘플은 이보다 작다. 대규모 데이터는 향후 Graph·Vector 검색으로 후보를 줄여 공급해야 한다.
기본 소켓 작업 시간 제한은 60초이며 전체 추천 완료 시간을 60초로 보장하는 제한은 아니다.

HTTP 리다이렉트를 거부한다. 키 오류·호출 한도·서버 오류·시간 초과·중간 연결 종료·응답 잘림·
JSON 오류를 구분하며 자동 재시도하지 않는다. 실패 전 완료된 모델 요청은 과금되었을 수 있다.
회사 근거가 REQUIRED인데 없으면 모델을 부르지 않는다. OPTIONAL이면 문항·경험만 비교한다.

## 검증 결과

2026-09-08, 최초 LLM/API 연결 시 Python 3.12.14에서 **82개 테스트 통과**:
기존 30개, 모의 의미 판단 24개, 모의 Solar HTTP 17개, 프로세스 내부 API 11개.
경험별 호출·분리 평가·상세 문항 연결과 오류 회귀 검증까지 포함한 현재 버전은 **전체 216개 통과**다.
API 의존성이 없는 Python에서는 API 테스트를 생략하므로 전체 검증에는 API·테스트 의존성이 필요하다.

`episode-common-plan`을 추천하는 테스트 응답은 미리 작성한 모의 데이터다. 통신 모의 테스트 성공은 Solar가
같은 판단을 한다는 증거가 아니다. [로컬 네 모델의 실제 비교·시연](w4-local-evaluation-v2-2026-09-08.md)은 완료했다.
상용 API 실제 비교, 사람의 정답 검토와 의미 오류 개선, W1/W2/W3·운영 인증·Graph·Vector 연동 검증이 남아 있다.
초기 연결 수정 사항은 [코드 리뷰](w4-llm-review.md)를 참조한다.

공식 근거:

- [Upstage Solar Pro 4 소개](https://www.upstage.ai/blog/en/solar-pro-4)
- [Upstage API Quickstart](https://github.com/UpstageAI/Solar-Pro4-Cookbook/blob/main/solar-agent-cookbook/quickstart.ipynb)
- [Upstage 파라미터 예제](https://github.com/UpstageAI/Solar-Pro4-Cookbook/tree/main/capabilities/parameters)
- [Upstage 구조화 출력 예제](https://github.com/UpstageAI/Solar-Pro4-Cookbook/tree/main/capabilities/structured-extraction)
- [FastAPI 라우터와 의존성](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [HTTPX의 프로세스 내부 ASGI 테스트](https://www.python-httpx.org/advanced/transports/#asgi-transport)
