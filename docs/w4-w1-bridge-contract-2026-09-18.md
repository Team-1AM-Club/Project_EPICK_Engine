# W1 실행 연결 계약과 적용할 코드

`epick_w4/w1_bridge.py`의 `W1ExecutionAdapter`가 W1의 `RecommendationExecutionPort.execute(owner_user_id, run_id)` 형태를 구현한다. 현재는 **가상 자료로 연결을 검증하는 코드**다. 실제 팀 PostgreSQL 저장소 구현이나 운영 승인을 완료했다는 뜻은 아니다.

## 확인한 W1 기준

2026-09-18 확인한 `Project_EPICK_Service`의 `feat/BE`는 `d50c4e9fa005959d344bbc13b4a8364a3eabce2f`, `develop`은 `afec08a9602132e5e433b523b0b6804850440524`다. 두 revision의 추천 실행기·서비스·DTO·모델·repository 5개 파일은 같다. `schemas/w1-candidate.pinned.schema.json`은 실제 W1 Pydantic 후보 DTO에서 얻은 스키마다. 당시 “백엔드가 비어 있음”은 현재 상황이 아니다.

현재 W1 `create_recommendation_run()`은 `result_origin="SYNTHETIC"`을 지정하고, 완료 함수도 `complete_synthetic_run()`이다. `SyntheticRecommendationAdapter`를 실제 모델 호출로 표시하거나, 그 완료 함수를 그대로 ENGINE Run에 적용하면 안 된다.

## 실행 흐름

1. 인증된 owner UUID와 Run UUID로 `RunStore.acquire()`를 호출한다. Run·문항 버전·snapshot·경험 버전과 실행권 토큰을 고정한다.
2. 고정한 snapshot의 경험 원문과 W3 C01 정보를 읽는다. 원문이 없으면 요약으로 바꾸지 않는다. 문항은 합의한 ID에만 연결한다.
3. W4가 경험별 추출 → 문항 판단 → 기업 Claim 판단 → Requirement의 개별 조건 판단을 실행한다. 각 모델 호출 전 권한·버전·Source 현재성을 재확인한다.
4. 코드가 원문 근거를 검사하고 조건 트리와 순위를 계산한다.
5. `publish()`가 최신 실행권·취소·삭제·동의·snapshot/문항 revision·Source 변경을 다시 확인한 뒤, 상세 본문·후보·상태를 한 트랜잭션으로 반영한다. 모델을 기다리는 동안 DB 행 잠금을 유지하지 않는다.

## 호스트가 구현할 RunStore

| 메서드 | 호스트의 책임 |
| --- | --- |
| `acquire(owner_user_id, run_id)` | owner 범위의 ENGINE PENDING Run을 짧은 트랜잭션으로 RUNNING으로 바꾸고 `RunBinding` 반환. 완료된 동일 Run은 재호출하지 않음. 동시 실행·없는 Run·철회는 거절 |
| `load_context(binding)` | 고정한 Run·문항·snapshot의 현재 원문과 C01 server context 0.2 조회. 현재 프로젝트의 다른 Run으로 대체하지 않음 |
| `authorize(binding, **action)` | PROCESS / SEND_TO_PROVIDER / RETURN_TO_CALLER별 현재 접근·삭제·동의·공급자 정책 검사 |
| `publish(binding, publication)` | 실행권과 revision이 여전히 같을 때만 전체 결과 게시. 후보 일부만 저장된 채 완료시키지 않음. Source의 로컬 무효화 epoch도 같은 게시 fence에 포함 |
| `fail(binding, code)` | 해당 실행권이 여전히 RUNNING일 때만 FAILED로 바꿈. CANCELLED나 다른 worker의 완료 상태를 덮어쓰지 않음 |

`RunBinding`의 `episode_versions`는 `(W4 episode_id, version) → W1 EpisodeVersion UUID`의 일대일 대응이다. 중복·누락·다른 snapshot 결과를 거절한다. `context_sha256`은 전체 문항·snapshot·원문·회사 revision에 해당하는 server context의 해시다. 호스트는 문항 버전, 정책 revision, Source epoch가 바뀌면 context도 바뀌도록 공급해야 한다.

## 저장할 내용과 상태

| W4 후보 상태 | W1 후보 상태 |
| --- | --- |
| DIRECT_MATCH | DIRECT_MATCH |
| PARTIAL_MATCH | PARTIAL_RELEVANCE |
| NEEDS_CONFIRMATION | NEEDS_VERIFICATION |

이 대응은 구현한 **검토용 정책**이다. 근거 부족을 일괄 `NO_RELEVANT_EVIDENCE`로 바꾸지 않는다. 문항·정답·모델 선정이 검토 전이므로 후보 validation과 Run/Result는 `LIMITED`로 기록한다. 구조 검사 통과를 `PASSED`로 확대하지 않는다.

`publication.candidates`는 `record_candidate()`에 전달할 후보 필드와 `internal_rank`를 포함한다. `episode_version_id`는 W1에서 UUID로 읽어 전달한다. owner와 run은 요청 본문이 아니라 고정한 binding에서 전달한다. 실제 Candidate ID는 W1 DB가 생성한 값을 사용한다.

`publication.full_result`에는 원문 위치·정확한 인용·문항별 상태·확인 질문·회사 근거·조건 트리·추론 모델 정보가 그대로 남는다. `source_dependencies`도 결과 revision에 연결해 보존한다. `result_version`은 Run·문항 버전·context·전체 결과로 만든 해시이며 Schema 이름과 다르다.

현재 W1 Candidate DTO는 요약 필드만 있으므로 **상세 결과와 의존성 저장 위치를 추가로 합의해야 한다.** 원문 본문을 애플리케이션 로그로 대신 저장하면 안 된다. 결과 재조회에도 권한·Source 현재성·만료를 검사해야 하며, W4 캐시 무효화만으로 W1 DB의 결과가 자동 삭제되지는 않는다.

## 로컬 연결 검증과 팀 적용의 차이

`examples/w4_w1_demo.py`의 `SyntheticRunStore`는 독립 SQLite에 합성 Run 하나를 저장하는 참조 구현이다. 실제 모델 결과의 W1 DTO 변환, 중복 실행, 게시 전 취소·철회·revision 변화, 게시 후 조회 차단을 검사하기 위한 것이다. 팀의 DB migration·실제 인증·worker·조회/선택 API를 대체하지 않는다.

팀에 필요한 적용 작업은 다음 네 가지다.

1. 서버가 선택한 실행 정책으로 ENGINE 합성 검증 Run을 접수하는 경로를 마련한다. 클라이언트가 임의 모델·owner·원문을 주입하게 하지 않는다.
2. 현재 W1 repository·권한 fence를 위 RunStore에 연결하고, 상세 결과·Source 의존성을 저장할 트랜잭션을 구현한다.
3. 위 상태 대응과 문항 ID 대응, 상세 결과 보관·삭제 정책을 검토한다.
4. 합성 통합용 서버에서 Run 접수 → worker 추론 → 저장 → 조회/선택 → 취소·제한 시 차단을 검증한다.

실제 사용자 자료는 계속 차단한다. 공식 지원서의 미확인 글자 수·필수 여부를 추론해서 입력 제한으로 만들지 않는다.
