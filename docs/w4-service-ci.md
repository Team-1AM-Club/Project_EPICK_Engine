# W4 서비스 CI와 결과 보관

2026-09-09 서비스 전달물 검토의 재현 요청을 반영했다. 검토 환경에서는 `httpx` 부재로 API 테스트를 import하지 못했다. CI는 `uv.lock`으로 API·test extra를 함께 설치하고 전체 테스트와 두 가상 HTTP 시연을 실행한다.

이 문서는 CI 구성과 재현 방법이다. GitHub에서 실행된 증거는 해당 Actions 실행과 그 산출물로 확인한다. 로컬 실행은 `execution_environment=LOCAL`, GitHub 실행은 `GITHUB_ACTIONS`로 기록하며 둘을 구분한다.

## 실행 조건과 범위

[워크플로](../.github/workflows/w4-service-ci.yml)는 `develop` 대상 PR, `develop` 또는 `feat/w4-service-handoff` 브랜치 push, 수동 dispatch에 반응한다. 저장소의 Actions 사용 설정이 필요하다. 수동 실행 메뉴는 워크플로가 기본 브랜치에 있어야 표시될 수 있으므로 처음에는 브랜치 push/PR 실행을 확인한다.

- Ubuntu 24.04/Python 3.12, Windows 2022/Python 3.13의 두 환경에서 각각 실행한다.
- uv 0.12.0으로 `uv sync --locked --extra api --extra test`를 실행한다. 환경 캐시 재사용을 끄고 잠금 파일을 갱신하지 않는다.
- 전체 unittest 발견·실행 수, 성공·실패·오류·skip을 기록한다. 이전 전달본의 249개보다 적게 발견되거나 하나라도 skip/실패/오류/expected failure가 있으면 실패한다. 테스트 수 하한은 발견 누락 방지용이며 의미적 커버리지를 보장하는 지표는 아니다.
- 두 시연은 HTTP 200, 응답 스키마, 기업 문맥 AVAILABLE/UNAVAILABLE, 각 추출 3회·판단 3회, 기존 검토 결과와의 JSON 일치를 검사한다.
- 시연은 `DemoBackend`와 `DemoClient`를 사용한다. 두 시연 합계 모의 호출 12회, 실제 모델 호출 0회다. 실제 W1·W3 연동이나 모델 정확도를 측정하지 않는다.

Actions는 공식 [checkout](https://github.com/actions/checkout), [setup-uv](https://github.com/astral-sh/setup-uv), [upload-artifact](https://github.com/actions/upload-artifact)의 확인한 커밋으로 고정했다. uv의 CI 설치 방식은 [공식 안내](https://docs.astral.sh/uv/guides/integration/github/)를 따른다.

## 로컬 재현

uv 0.12.0을 준비하고 저장소 루트에서 실행한다. 아래 명령은 Windows PowerShell과 Bash에서 같다.

```text
uv sync --locked --extra api --extra test
uv run --locked --extra api --extra test python scripts/verify_service_handoff.py --output-dir output/ci/local-01
```

매번 새로운 출력 폴더 이름을 사용한다. 이미 존재하는 폴더는 이전 성공 기록이 섞이지 않도록 거부한다. 가상 시연만 다시 실행하려면 다음 명령을 사용한다.

```text
uv run --locked --extra api --extra test python scripts/demo-service-handoff.py --output-dir output/demo-local-01
```

CI와 동일한 의존성 버전 재현에는 위 잠금 설치를 사용한다. `pip install -e ".[api,test]"`는 개발 편의용이며 `uv.lock`의 버전을 보장하지 않는다.

## 산출물 읽는 방법

GitHub Actions 실행의 Artifacts에서 `w4-service-OS-py버전-실행ID-재시도번호`를 받는다. 성공·실패 모두 업로드를 시도하며 14일 보관한다. 오래 보관할 결과는 만료 전에 다운로드한다. 설치 실패 시에는 설치 로그만 존재할 수 있으며 이를 테스트 통과로 해석하지 않는다.

| 파일 | 확인할 내용 |
|---|---|
| `install.log`, `uv-version.txt` | 잠금 의존성 설치 성공 여부, uv 버전. GitHub 설치 단계에서 생성 |
| `verification/summary.json` | 전체 상태, LOCAL/GITHUB_ACTIONS, GitHub 실행·커밋 식별자, 테스트·시연 결과, 미실행 운영 검증 |
| `verification/environment.json` | 실제 Python·OS와 pydantic/fastapi/httpx 버전 |
| `verification/source-sha256.json` | 실행한 코드·테스트·샘플·스키마·워크플로·잠금 파일의 바이트 해시 |
| `verification/tests.json`, `tests.log` | 성공한 테스트 ID, 실패·skip 목록과 실행 로그 |
| `verification/demos/demo-summary.json`, `demos.log` | 두 시연 검증과 모의 호출 수 |
| `verification/demos/synthetic-company.json` | 가상 기업 근거를 경험과 연결한 추천 |
| `verification/demos/diagnostic-company.json` | 사용 불가 기업 근거의 제한을 보존한 추천 |
| `verification/error.log` | 실행 도구 자체가 예외로 중단된 경우에만 생성 |

`summary.json`의 PASSED는 해당 입력·해시로 테스트와 가상 시연이 성공했다는 뜻이다. GitHub 실행의 전체 성공 여부와 함께 확인한다. 문항 해석 초안, 운영 모델 보류, 실제 데이터 차단은 계속 유지한다.

## 이 검토에서 남은 일

[D-05 합의 요청](w4-d05-contract-decisions.md)에 버전·Evidence·restriction·index ACK, 날짜 미상·첨부·부분 추출 정책, W1 실연동의 수용 사례를 정리했다. 현재 로컬 투영을 채택한 것으로 표시하지 않으며, 실제 W1 저장소 구현체의 통합 결과는 별도 검증이 필요하다.
