# W1 백엔드 최신 확인과 W4 연결 작업

2026-09-17. **백엔드의 추천 API·저장 구조는 구현됐고, 실제 W4 실행·결과 저장 연결은 추가 작업이 필요하다.** 이전 9월 9일의 “백엔드 파일이 비어 있음”은 당시 기록이다.

## 확인한 기준과 검사

GitHub에서 `feat/BE`의 `d50c4e9fa005959d344bbc13b4a8364a3eabce2f`, `develop`의 `3d3ba0815eae86293c5f4596f81ac1f2923c33d4`를 확인했다. W3 브랜치도 정본과 같은 `05f26b4c0a52aecf155a66df0fcaa38e6fbd4cf5`였다. `feat/BE`를 별도 조사 폴더에 받았으며 팀 저장소의 코드를 수정하지 않았다. 두 백엔드 revision 사이의 차이는 실행 환경 preflight·격리 시연·권한/worker 관련이며, 여기서 대조한 추천 DTO와 실행기는 같다.

- [실제 DTO 대조와 소스 해시](../output/w1-connection-audit-20260917/audit.json)
- [백엔드 Candidate Schema](../output/w1-connection-audit-20260917/w1-candidate.schema.json)
- [백엔드 Run Schema](../output/w1-connection-audit-20260917/w1-run.schema.json)
- [백엔드 실행기 원본](https://github.com/Team-1AM-Club/Project_EPICK_Service/blob/d50c4e9fa005959d344bbc13b4a8364a3eabce2f/backend/app/services/recommendation_execution.py)

W4 결과의 후보 3개를 실제 백엔드 Pydantic DTO에 그대로 넣으면 모두 거부된다. 예상된 계약 차이이며 백엔드 결함이라고 판정하지 않는다. `DIRECT_MATCH`는 허용되지만 `PARTIAL_MATCH`, `NEEDS_CONFIRMATION`은 현재 W1 후보 상태에 없다. 이 검사는 Schema와 문자열 타입을 실행한 검사다. 실제 W1 서버·인증·DB에 요청하지 않았다.

## 이미 준비된 W1 기능

`POST /api/v1/questions/{question_id}/recommendation-runs`는 사용자 범위, 문항 버전, snapshot 버전, idempotency key를 처리하고 합성 Run을 접수한다. Run·Candidate 조회와 선택 API, owner와 snapshot에 묶인 저장 함수도 있다.

`RecommendationExecutionPort.execute(owner_user_id, run_id)`가 실행 연결 지점이다. 현재 구현체 `SyntheticRecommendationAdapter`는 snapshot의 경험들을 정해진 순서로 읽어 합성 후보를 기록한다. 실제 W4 추론·C01 근거·외부 전송 계약을 연결한 구현체는 아니다. 이 실행기의 결과를 실제 LLM 결과로 표시하면 안 된다.

`record_candidate()`는 owner와 snapshot에 포함된 `episode_version_id`를 확인한다. 이것만 호출해 전체 실행의 권한·삭제·버전·기업 제한 검사가 끝났다고 취급하지 않는다. 마지막 결과 게시와 이후 재조회에도 검사가 필요하다.

## 연결할 순서

### 1. W1 Run에 묶인 입력 조회

호스트가 신뢰한 `owner_user_id + run_id`로 문항·snapshot·경험 버전을 한 실행에 고정한다. W4 공개 요청에 원문, 소유자, 기업 지식을 추가하지 않는다. 현재 `Backend.load_context(user_id, project_id)` 구현체를 Run별로 묶어 만들거나, 별도 서버 내부 호출 계약을 합의한다. project만으로 여러 Run·문항 중 하나를 추측해서는 안 된다.

| W1 자료 | W4로 공급할 값 | 필요한 처리 |
|---|---|---|
| Run/project/owner UUID | project와 context_version | 서버 범위 검사, 문항·snapshot·정책 revision을 context에 반영 |
| QuestionVersion UUID·문항 내용 | question selector / 구조화된 문항 기준 | 기존 5문항 초안 ID와의 대응을 명시. 임의 문항을 가장 비슷한 ID로 바꾸지 않음 |
| snapshot에 고정된 EpisodeVersion | episode_id, version, owner_id, activity_id, title, raw_text | `original_narrative`의 원문·경계를 보존. null 원문을 요약 필드로 대체하지 않음 |
| EpisodeVersion의 UUID | 결과 저장용 ID 대응표 | W4의 `episode_id + version`과 원래 UUID를 함께 보관 |
| W3 C01 signal·StructureResponse | server context 0.2의 company_knowledge | 처리 시작 generation, 정확한 Source/IndexKey, 명시적인 host metadata 필요 |

경험 원문·소유 범위·제외·동의 상태, 질문 revision을 확정할 수 없는 입력은 추측해 연결하지 않는다. 현재 실제 데이터 전송은 계속 차단되어 있다. 최초 통합은 별도 합성 Run에서 검증한다.

### 2. 모델 호출과 반환 권한 재검사

W1의 현재 권한·삭제 epoch/fence·동의·snapshot 상태를 W4 `authorize(PROCESS / SEND_TO_PROVIDER / RETURN_TO_CALLER)`에 연결한다. C01 consumer의 모든 Source 현재성 검사도 함께 실행한다. 모델을 기다리는 동안 DB 행 잠금을 장시간 유지하는 방식은 피하고, 결과 반영 시 고정한 revision과 최신 권한을 다시 대조한다.

### 3. 상태와 결과 저장 계약 확정

아래는 **대응 제안이며 아직 적용·승인하지 않았다.**

| W4 상태 | W1 후보 상태 제안 | 확인할 의미 |
|---|---|---|
| DIRECT_MATCH | DIRECT_MATCH | 문항 기준 전체의 원문 근거가 확인됨 |
| PARTIAL_MATCH | PARTIAL_RELEVANCE | 일부 내용의 근거가 있으나 전체 요구는 미충족 |
| NEEDS_CONFIRMATION | NEEDS_VERIFICATION | 불명확·충돌·근거 부족 사유를 함께 보존 |
| 해당 값 없음 | NO_RELEVANT_EVIDENCE | NEEDS_CONFIRMATION 전체를 이 값으로 바꾸지 않음. 필요하면 별도 조건 정의 |

`validation_status=PASSED`는 근거 관련성이나 JSON 정상만으로 자동 지정하지 않는다. W1·W4가 PASSED/LIMITED/FAILED의 의미를 합의해야 한다. W4 `processing_status`와 W1 Run/Result 상태의 대응, 오류·취소·기한 만료도 별도다.

W1 Candidate DTO는 짧은 요약만 저장/표시하는 형태다. W4 0.3의 문항 점검·확인 질문·원문 위치·Source 의존성·조건 트리·제한 사유는 별도 결과 본문으로 보관하고 Candidate와 정확한 결과 revision으로 연결해야 한다. Schema 이름 하나를 실행 결과 version으로 재사용하지 않는다.

### 4. 원자적 반영과 무효화 확인

모든 후보를 반영하고 Run을 완료시키는 게시 트랜잭션을 정의한다. W4 응답 수신이나 W3 처리 ACK를 W1 게시 완료 ACK로 간주하지 않는다. Source 변경 시 W4 캐시뿐 아니라 W1에 저장한 관련 결과도 조회 차단·무효화해야 한다. 삭제/권한 철회가 모델 호출 이후에 발생하는 경우, 중복 완료와 취소 경쟁도 검사한다.

## 팀에 확인받을 구체적인 사항

1. W1의 Run 기반 Engine 실행기와 서버 내부 context 공급 담당·호출 방식을 정한다.
2. 위 후보 상태와 validation/run 상태 대응, 상세 결과 본문의 저장 위치·result_version 규칙을 확인한다.
3. C01 metadata 공급자, Source restriction 순번 단위, P4/P5, 운영 보관·삭제 정책을 확정한다.
4. 합성 통합용 서버/DB와 실행 자격을 준비한다. 자격증명은 채팅이나 샘플 파일에 넣지 않는다.

이 네 항목을 합의하면 실제 W1 Run 접수 → W4 추론 → 후보 저장 → 조회/선택 → 제한 시 차단을 시험한다. 현재 Graph/SkillAlias capability 호환 테스트가 있다는 사실만으로 W4 추천 계약까지 호환된다고 간주하지 않는다.
