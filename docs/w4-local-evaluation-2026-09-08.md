# W4 실제 로컬 LLM 비교 결과

이 문서는 Qwen3-4B·Granite Micro로 실행한 **이전 v1 결과**를 보존한다.
경험별 호출로 수정한 후의 네 모델 성적과 완성된 추천 시연은 [v2 실제 비교 보고서](w4-local-evaluation-v2-2026-09-08.md)에 있다.

2026-09-08, RTX 5080 16GB에서 **Qwen3-4B와 IBM Granite 4.0 Micro의 실제 추론을 실행했다.**
모두 공식 공개 Q4_K_M 가중치이며 Solar·GPT·Claude API를 호출한 결과가 아니다.
실제 평가 요청 228회와 별도 통합 시연 요청 20회, 총 248회의 응답·실패를 보존했다. 유료 API는 사용하지 않았다.

**현재 설정에서는 추천용 모델을 확정할 수 없다.** 두 모델 모두 문항·매칭 종합 점수가 같았고,
경험 매칭에서는 입력 후보를 누락했다. 원문 추출을 실제로 실행해 다음 단계까지 넘겼으나,
최종 추천은 검증 오류로 중단됐다. 추천 성공 시연이나 운영 준비 완료로 제시하면 안 된다.

## 동일한 출력 스키마를 적용한 두 번째 실행

아래 값은 **검토 전 정답 초안과의 완전 일치율**이다. 일반적인 한국어 이해 능력이나 전체 추천 정확도가 아니다.
원문 추출은 각 구간의 종류·주체·서술 상태·문제 코드가 모두 일치해야 정답으로 센다.

| 항목 | Qwen3-4B Q4_K_M | Granite 4.0 Micro Q4_K_M |
|---|---:|---:|
| 문항 전체 일치 | 12.50% (3/24) | 12.50% (3/24) |
| 매칭 전체 일치 | 0.00% (0/21) | 0.00% (0/21) |
| 문항·매칭 종합, 기존 50:50 초안 | 6.25 | 6.25 |
| 추출 구간 전체 일치 | 36.84% (21/57) | 10.53% (6/57) |
| 추출 종류 F1, 별도 진단 | 68.09% | 48.48% |
| 추출 주체 일치 | 89.47% | 78.95% |
| 추출 서술 상태 일치 | 94.74% | 94.74% |
| 평가 중 HTTP·JSON 파싱 실패 | 0/57 | 0/57 |
| 평가 요청 시간 중앙값 | 0.72초 | 0.81초 |

각 모델은 문항 8개·매칭 7개·원문 4개를 각각 3회 실행했다. 원문은 총 19구간이므로 반복 포함 57구간이다.
시간은 이 PC의 해당 평가 요청에 한정되며 모델 로딩·다운로드와 별도 시연을 포함하지 않는다.
JSON 파싱 성공 이후의 후보 ID·개수·근거 검사는 별도다. 파싱 실패가 0이라고 매칭이 성공한 것은 아니다.

- [문항·매칭 보고서](../output/local-evaluation-20260908-02-structured/question-matching-report.json)
- [원문 추출 별도 보고서](../output/local-evaluation-20260908-02-structured/extraction-report.json)
- [실행 시간](../output/local-evaluation-20260908-02-structured/performance.json)
- [Qwen 실제 HTTP 요청·응답](../output/local-evaluation-20260908-02-structured/qwen3-4b-q4-k-m/http-traces.json)
- [Granite 실제 HTTP 요청·응답](../output/local-evaluation-20260908-02-structured/granite-4-micro-q4-k-m/http-traces.json)

## 실패 원인과 해석

**매칭:** 두 모델 모두 21회의 매칭 요청 각각에서 후보 2개를 받고 1개만 반환했다.
검증기는 이를 `INCOMPLETE_CANDIDATES`로 거부한다. 누락된 후보를 코드가 추정하거나 정답으로 채우지 않았다.
따라서 0%는 모든 관련성 판단이 틀렸다는 뜻이 아니라, 전체 응답 계약을 만족한 사례가 없다는 뜻이다.

**문항:** 인용 범위를 정답 초안보다 넓게 선택하면 현재 완전 일치 채점에서 오답이 된다.
예를 들어 Qwen은 ‘상반된 입장을 가진 구성원들이 같은 결론에 도달하도록 기여’하는 문항을
`collaboration`으로 분류했지만, 문항 전체를 인용해 정답 초안의 인용 범위와 달랐다.
동시에 복합 문항에서 문제 해결 기준을 빠뜨리거나 책임감·사용자 관점을 다른 기준으로 분류하는 오류도 확인했다.
타당한 인용 변형에 대한 사람의 검토가 필요하며, 결과를 본 뒤 이번 정답을 수정해 점수를 올리지는 않았다.

**추출:** Qwen의 구간 분류 일치율이 더 높았다. 하지만 4개의 단순한 가상 경험과 미검토 분류 초안에 대한 결과다.
종류를 더 넓게 붙이는 해석 차이도 오답에 포함된다. 이 점수만으로 최종 추천 모델을 고르지 않는다.
원문 문자열·위치를 코드가 그대로 복사하는 검사는 LLM의 추출 정확도 점수에 합산하지 않았다.

## 원문부터 추천까지 실제 실행한 결과

두 번째 실행에서 모델별로 원문 4개를 새로 추출한 뒤, 그 결과를 협업·학습 추천기에 실제 입력했다.
정답 초안이나 첫 비교의 응답을 재생한 것이 아니다.

- [Qwen 실제 추출 결과](../output/local-evaluation-20260908-02-structured/qwen3-4b-q4-k-m/live-extraction.json): Fact 13개. 전부 원문 위치와 문자열이 일치하는 것을 확인했다.
- [Granite 실제 추출 결과](../output/local-evaluation-20260908-02-structured/granite-4-micro-q4-k-m/live-extraction.json): Fact 25개. 전부 원문 위치와 문자열이 일치하는 것을 확인했다.
- Qwen 협업·학습: `LLM_INCOMPLETE_CANDIDATE_SET`으로 추천 중단.
- Granite 협업: `LLM_INCOMPLETE_CANDIDATE_SET`, 학습: `LLM_INVALID_EPISODE_REFERENCE`로 추천 중단.

발췌가 원문에 존재한다는 사실과 모델이 역할·행동·결과를 올바르게 분류했다는 결론은 다르다.
Fact 개수가 많을수록 좋다는 의미도 아니다. 기존의 문항별 상세 기준 초안 통합은 별도 후속 작업이다.

## 첫 실행과 변경 범위

[첫 실행 기록](../output/local-evaluation-20260908-01/question-matching-report.json)도 보존했다.
단순 JSON 모드에서는 Qwen 평가 요청 57회 중 15회, Granite는 12회가 JSON 파싱에 실패했다.
첫 실행의 추출 전체 일치율은 Qwen 31.58%, Granite 0%였다. Granite의 0%에는 파싱 이후 스키마 검사 실패도 포함된다.

두 번째 실행에서는 **두 모델 모두 같은 W4 JSON 스키마**를 적용했다. 형식·허용 라벨을 제한하며
정답, 올바른 후보 선택, 기준 연결은 스키마에 포함하지 않았다. 문항·원문·정답·채점 방식은 그대로다.
이 변경으로 JSON 오류는 사라졌으나 후보 누락은 해결되지 않았다. 모델별로 유리한 실행만 섞어 비교하지 않았다.

## 실행 조건과 재현

- 실행기: llama.cpp b10859, commit `ca86fb222`, Windows CUDA 13.3.
- 공통 조건: context 16,384, 단일 슬롯, temperature 0, seed 42, 출력 최대 4,096토큰, 추론 모드 끔.
- 고정 seed·greedy 반복은 서로 독립인 새 사례가 아니므로 일반화나 통계적 우월성의 근거로 삼지 않는다.
- 공식 모델 revision·파일 SHA-256·실행기 체크섬은 [고정 목록](../samples/evaluation/local-models.json)에 있다.
- [Qwen 공식 모델](https://huggingface.co/Qwen/Qwen3-4B-GGUF), [IBM 공식 모델](https://huggingface.co/ibm-granite/granite-4.0-micro-GGUF), [llama.cpp 출력 형식 안내](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)를 확인했다.
- 모델·실행기는 C:의 임시 폴더 `epick-w4-local-models-b10859`에 둔다. Google Drive에는 코드와 작은 실행 결과만 저장한다.
- 추론 서버는 `127.0.0.1:18080`에서 실행하고 작업 후 종료했다. 입력은 허용 목록에 있는 가상 데이터만 사용했다.

Windows NVIDIA GPU 환경에서 저장소 루트 기준:

```powershell
python scripts/prepare-local-models.py
python scripts/run-local-evaluation.py --output-dir output/local-baseline-new
python scripts/run-local-evaluation.py --structured --output-dir output/local-structured-new
```

실행 결과 폴더는 새 경로를 지정한다. 모델 다운로드는 약 4.6GB, 실행기 압축 파일은 약 0.54GB이며
이미 있는 파일은 크기·SHA-256을 검증해 재사용한다. 다른 PC에는 해당 GPU 실행 환경이 필요하다.

기존 평가기의 기본 승인 조건은 유지했다. 명시적인 `exploratory=True`에서만 실제 응답을 초안과 비교할 수 있고,
추천은 항상 `WITHHELD`다. 실제 응답은 `CAPTURED`로 기록하며 모의 응답으로 표시하지 않는다.
정답·가중치 승인 기록을 생성하지 않았고, 추출 점수를 문항·매칭 종합 점수에 합산하지 않았다.

## 검증과 다음 작업

코드 테스트 **174개 통과**, `git diff --check` 통과. 테스트는 코드 동작 검증이며 위 실제 모델 성적과 별개다.
모델 파일과 실행기 다운로드 체크섬을 검증했고, 실제 요청·응답·서버 설정·로그·실패를 보존했다.

다음 개발 과제는 후보 전체를 반환하도록 호출·출력 계약을 보강하고 ID 오류를 줄이는 것이다.
정답 인용 변형과 추출 라벨을 사람이 검토한 뒤 독립 사례로 다시 평가해야 한다.
상용 API 모델까지 비교하려면 별도의 API 접근 권한과 해당 공급자 어댑터가 필요하다.
