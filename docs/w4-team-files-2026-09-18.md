# 팀 전달 파일 안내

먼저 [진행 결과와 모델 비교](w4-staged-result-2026-09-18.md)를 읽고, [W1 연결 계약](w4-w1-bridge-contract-2026-09-18.md)을 확인하면 된다. 운영 모델 선정은 보류했고 실제 팀 서버·PostgreSQL 연동은 미실행이다. 아래 시연은 **가상 데이터와 실제 로컬 LLM**을 사용했다.

## 전달할 문서·샘플·결과

| 파일 | 기능 |
| --- | --- |
| `docs/w4-staged-result-2026-09-18.md` | 5단계 설명, 네 모델 비교, 추출 점수, 실제 시연 성공·실패, 검증과 한계 |
| `docs/w4-w1-bridge-contract-2026-09-18.md` | W1 실행 연결 지점, RunStore 책임, 상태·UUID 대응, 상세 결과 저장 계약 |
| `docs/w4-workflow.md` | 현재 작업 순서와 남은 팀 작업 |
| `samples/c01/fresh-input.synthetic.json` | 새 가상 경험 6개의 원문 입력 |
| `samples/c01/fresh-reference.v1.draft.json` | 호출 전에 고정한 문항·기업 조건·인용의 정답 초안 |
| `samples/c01/fresh-extraction-reference.draft.json` | 원문 구간 분류의 정답 초안. 사람 승인 전 |
| `output/c01-staged-evaluation-20260918/run-2/` | 네 모델의 실제 응답·점수·고정 프로토콜·추출 결과 |
| `output/c01-staged-evaluation-20260918/final-demo/` | 기존 7개 회귀, 성공한 HTTP 시연, Qwen 9B의 W1 품질 실패 기록 |
| `output/c01-staged-evaluation-20260918/w1-recheck/` | Gemma 12B→Gemma 26B의 W1 연결 결과. `publication.json`은 상세 저장 본문, `candidate-responses.json`은 W1 후보 DTO |
| `output/c01-staged-evaluation-20260918/verification-final/` | 351개 로컬 테스트와 모의 HTTP 회귀 기록 |
| `output/c01-staged-evaluation-20260918/audit-final/verification.json` | 실제 송신 입력·모델·Schema·W1 DTO 대조와 호출 수 집계 |

## 핵심 코드

`api.py`만 복사해서는 실행할 수 없다. `epick_w4/` 전체와 패키지 JSON 자료, 의존성 설정이 함께 필요하다.

| 파일 | 기능 |
| --- | --- |
| `epick_w4/api.py` | FastAPI 진입점. 신뢰한 인증·backend·추출/판단 client factory 주입 |
| `epick_w4/service_adapter.py` | 서버 원문 조회, 매 호출/반환 권한 검사, 결과 검증, 모델별 캐시 분리 |
| `epick_w4/w1_bridge.py` | `execute(owner_user_id, run_id)` 구현. Run/snapshot/UUID 대응, W1 후보와 상세 저장 본문 생성 |
| `epick_w4/c01_staged.py` | 문항·기업 Claim·Requirement를 나눠 호출하고 결과를 결합하는 새 경로 |
| `epick_w4/c01_detail.py` | 조건별 근거 검사와 AND/OR 결합. 과거 통합 호출 경로도 재현용으로 유지 |
| `epick_w4/detailed_recommendation.py` | 추출 결과를 실제 원문과 대조하고 상태·확인 질문·정렬을 계산 |
| `epick_w4/evidence_extraction.py` | 원문을 고정 구간으로 나누고 분류 응답의 주체·서술 상태·근거를 검증 |
| `epick_w4/c01_adapter.py` | W3 C01 정본·출처·조건 트리를 W4 내부 기준으로 읽음 |
| `epick_w4/c01_consumer.py` | Source 현재성, 제한 신호·ACK·결과 캐시 무효화·만료 처리 |
| `epick_w4/local_client.py` | 로컬 llama.cpp 실제 호출, 모델·출력·시간 제한 검사 |
| `epick_w4/synthetic_policy.py` 및 `*_allowlist.json` | 사전 등록된 가상 문항·원문·기업 정보만 모델에 보내도록 제한 |
| `epick_w4/c01_contract.py`, `handoff_contract.py`, `schemas/` | API와 내부 전달 계약. W1 후보 스키마 사본은 DTO 대조용 |
| `examples/w4_w1_demo.py` | 합성 Run의 SQLite 참조 저장소. 팀 PostgreSQL repository 구현은 아님 |
| `examples/w4_c01_fresh_demo.py` | 새 가상 사례와 정답 초안 생성 규칙 |
| `scripts/run-c01-staged-evaluation.py` | 네 모델의 새 사례 비교. 모델 가중치·설정·원본 응답 기록 |
| `scripts/run-c01-final-demo.py` | 기존 사례 회귀, 두 모델을 차례로 올려 HTTP/W1 경로 실제 시연 |
| `scripts/audit-c01-staged-delivery.py` | 이 PC의 평가 기록과 별도 W1 조사 checkout을 대조하는 감사 도구 |
| `scripts/verify_service_handoff.py` | 모델 서버 없이 전체 테스트와 모의 HTTP 시연 실행 |
| `tests/test_c01_staged*.py`, `tests/test_w1_bridge.py` | 호출 분리·채점·캐시와 W1 실행/게시/조회 경계 검사 |
| `pyproject.toml`, `uv.lock` | 패키지와 잠금 의존성. 기존 CI는 유지하지만 이번 변경의 원격 CI는 미실행 |

## 재현

Python과 uv가 설치된 새 폴더에서 다음과 같이 실행한다.

```powershell
uv sync --locked --extra api --extra test
uv run python scripts/verify_service_handoff.py --output-dir output/local-check-new
```

위 검사는 실제 모델 호출을 하지 않는다. 실제 비교·시연에는 `samples/evaluation/local-models.v2.json`의 GGUF 파일과 같은 SHA의 로컬 모델, llama.cpp 실행 파일이 필요하다. 해당 파일들은 ZIP에 포함하지 않았다. 모델 경로는 실행 PC에 맞춰 설정하고 과거 결과 폴더를 출력 위치로 재사용하지 않는다.

```powershell
uv run python scripts/run-c01-staged-evaluation.py --runtime 'C:/path/to/llama-server.exe' --output-dir output/staged-new
uv run python scripts/run-c01-final-demo.py --w1-only --runtime 'C:/path/to/llama-server.exe' --output-dir output/w1-new
```

일반 서비스는 `create_service_router(..., c01_split=True)`로 새 판단 경로를 선택한다. 요청 본문이 모델이나 판단 모드를 선택하지 않는다. W1 연결 어댑터는 새 경로를 사용한다. 실사용 자료를 허용하려고 가상 데이터 제한을 임의로 제거하지 말고, 동의·보관·전송 정책과 별도 검증을 먼저 합의한다.

ZIP의 `MANIFEST.json`은 포함 파일의 SHA256이다. 가상 DB 파일·모델 가중치·API 키·가상환경·Git 저장소는 포함하지 않는다. 평가의 첫 실행기 오류 이력도 `run-1` 기록으로 보존하되 최종 성능 점수에는 합산하지 않았다.
