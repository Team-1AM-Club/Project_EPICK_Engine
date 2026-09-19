# W1 회사 연결 수정과 W4 로컬 통합 검증

상태: **LOCAL_PARTIAL_INTEGRATION / 팀 채택 전 / 공동 CT-12 미실행**.

사용자가 전체 단계 진행을 요청했고, W1 회신·공동 환경이 아직 없으므로 로컬 수정·통합 검증을 진행하되 팀 합의와 공동 검증은 미완료로 표시하기로 확인했다. 외부 발송·commit·push·배포·운영 DB 변경은 수행하지 않았다.

## 결과

| 요청 단계 | 이번에 완료한 범위 | 남아 있는 범위 |
| --- | --- | --- |
| W1 회사 ID 충돌 수정 | 별도 Service 브랜치에서 현재 DB 관계로 회사 UUID를 확인하도록 수정. 정상·변조·버전 변경·권한·명령 연결 검사 | W1 검토/채택, 실제 PostgreSQL 권한·RLS·동시성 검증 및 배포 |
| 판단 정책·전송 책임 합의 | 아래에 판단 원칙과 W4/W1/W2 책임·채택 항목을 구체화 | 팀원들의 실제 채택 회신. 합의됐다고 표시하지 않음 |
| 공동 CT-12 검증 | W4 생성기와 실제 W1 worker·relay·조회 함수의 로컬 부분 통합 9개 확인 | W4 수신·영속 저장 경로, outbox 재시작 내구성, 격리 PostgreSQL/SQS, 정본 runbook으로 공동 실행 |

Service의 `tests/contract`, `tests/runtime`, `tests/test_health.py` **203개 통과, 실패/오류/skip 0**. 새 질문용 테스트는 38개다. SQLite로 실제 관계 조회 SQL과 ASGI 조회 경로를 실행했다. 기존 W4의 381개 전체 검사는 이전 단계 기록이며 이번 결과에 합산하지 않는다. 이번에는 실제 모델을 호출하지 않았다.

## 변경 기준과 파일

기존 참조본을 보존하고 `Project_EPICK_Service_W4/`에 `feat/w4-question-core-binding` 작업 브랜치를 만들었다. 기준은 [Service develop 41dd0c21692c7f59c87962cf1e7d2746bac73303](https://github.com/Team-1AM-Club/Project_EPICK_Service/tree/41dd0c21692c7f59c87962cf1e7d2746bac73303)이다. 로컬 변경은 미커밋이며 이 기준 SHA만 checkout하면 새 수정은 없다.

아래 Service 경로는 `Project_EPICK_Service_W4/` 기준이다.

| 파일 | 기능 |
| --- | --- |
| `backend/app/runtime/question_core_binding.py` | 현재 Job/owner/project/question/Source 관계로 회사 확인. 보관·오래된 프로젝트, 바뀐 문항, 다른 회사·소유자·입력 버전·연결된 명령 거부 |
| `backend/app/runtime/core_decision_binding.py` | question pin의 null과 수집 company UUID를 구분. 외부에서 추정한 회사가 아니라 위 조회 결과를 요구하고 Source link의 owner/Job/입력/purpose 결속도 검사 |
| `backend/app/runtime/workers.py` | COMPANY_KNOWLEDGE뿐 아니라 QUESTION_MATCHING의 수집 명령 생성. question pin의 회사는 null 유지 |
| `backend/app/runtime/outbox_relay.py` | publish 전 현재 관계와 해당 command에 연결된 Source 재검사 |
| `backend/app/runtime/lookup_adapter.py` | 실제 W2 전용 조회 route에서 동일 회사·owner/project/Job/purpose/command 관계와 기존 fence·삭제 검사 |
| `backend/infra/postgres/runtime_privileges.sql` | 필요한 ID·상태 컬럼만 worker/lookup 역할에 읽기 허용하는 변경안 |
| `backend/migrations/versions/027_question_core_binding_read.py` | 새 조회에 필요한 SELECT RLS 정책. 로그인·쓰기·BYPASSRLS 권한을 추가하지 않음 |
| `backend/contracts/fixtures/v1/w1/private-w2-question-command-dispatch.json` | question pin company null + W2 company UUID가 함께 유효한 정상 fixture |
| `backend/tests/runtime/test_question_core_binding.py` | 새 계약·SQL 관계·worker·relay·ASGI 경계 테스트와 명시적인 합성 저장 어댑터 |
| `backend/uv.lock` | 이번 재현 환경의 잠금 의존성 |

Engine의 추가 파일은 [로컬 연결 실행기](../scripts/verify-question-core-integration.py)다. 기존의 W4 pinned schema와 과거 실패 재현 fixture는 당시 증거로 보존했다. W1/W2 wire schema를 바꿀 필요 없이 현재 관계 조회를 추가했으며, schema만으로 표현할 수 없는 company 교차 검사는 runtime이 담당한다.

## 회사 연결 규칙

1. W4가 전달하는 문항용 Core Decision과 W1의 immutable pin에서 `company_id=null`은 유지한다.
2. W1은 Job owner와 project, 현재 ProjectVersion의 company, 현재 QuestionVersion, JobSourceLink의 Source/입력 버전을 결속한다. Source의 company와 ProjectVersion의 company가 같아야 한다.
3. 결정 버전은 W2의 세 정수 revision 필드에 대응한다. 원본 `analysis_input_version` 문자열을 숫자로 해석하지 않는다.
4. relay/조회에서는 Source link의 command ID와 purpose ID도 확인한다. 삭제·재지정·다른 owner·다른 프로젝트·바뀐 문항은 차단한다.
5. 기존 COMPANY_KNOWLEDGE 회사 동일성 검사는 유지한다. W2 command company를 null로 보내거나 비교 검사를 삭제하는 우회는 없다.

PostgreSQL 운영 적용에는 **마이그레이션 027과 컬럼 권한 SQL을 코드 배포 전에 함께 적용**해야 한다. 이번에는 Alembic이 해당 구간의 SQL을 정상 생성하는 것까지만 확인했다. 실제 PostgreSQL/RLS 적용, 최소 권한 로그인 접속, 트랜잭션 lock 경쟁·취소/삭제 경쟁은 미검증이다. SQLite 성공으로 이를 대체하지 않는다.

## 판단 정책·전송 책임 제안

아래는 실제 팀 합의가 아니라 검토 가능한 채택안이다. 응답은 항목별 `채택 / 수정 / 보류`로 받는다.

| ID | 제안 |
| --- | --- |
| P1 판단 근거 | W4는 문항의 평가 기준에 필요한 Source를 명시적인 판단 근거와 함께 지정한다. 현재 자동 판단은 끄고 호스트가 명시적으로 지정한 결정만 생성한다. LLM SUPPORTED, 경험 1순위, C01 USABLE을 Core로 자동 변환하지 않는다. |
| P2 필수/보조/보류 | 문항 평가에 필수인 자료는 CORE_REQUIRED, 맥락 보완은 NON_CORE_OPTIONAL. 기준이나 역할이 불명확하면 임의로 어느 쪽으로도 발행하지 않고 보류한다. 누가 어떤 기준을 승인하는지는 W4/팀 검토로 확정한다. |
| P3 reason | QUESTION_EVIDENCE_REQUIRED와 SUPPLEMENTARY_CONTEXT를 초안으로 제안한다. 첫 번째 코드는 가상 시연용이며 팀 채택 전이다. 원문·개인정보를 reason_code에 넣지 않는다. |
| T1 W4 | 문항/Source에 대한 의미 판단·근거, 동일 제출 ID/시각/본문 보존, 발행 직전 현재성 재검사. 실제 내구성 outbox 및 전송 adapter 담당/구현은 합의 필요. |
| T2 W1 | 인증 principal/channel과 owner/Job/문항/Source 관계, 입력·결정 버전 충돌, 회사 조회, receipt, inbox와 원자 저장, 취소·삭제 fence, 실행 명령 및 relay 책임. |
| T3 W2 | W1이 승인한 명령을 받은 뒤 protected lookup으로 현재 권한을 확인하고 수집·commit gate 계약 수행. W4 Core receipt를 수집 완료로 해석하지 않음. |
| T4 W3 | 분석된 지식·사용 가능성 제공. W4 Core inbound나 W2 ACK를 C01 usability 계약으로 대체하지 않음. |
| T5 재실행 | Core 수신 자체로 수집 작업을 자동 재개하지 않는 기존 W1 경계를 유지한다. 실제 user retry/실행 전환 조건은 W1 정본을 따른다. |

특히 최신 W1에는 W3 전용 수신 worker와 job_id를 포함한 W3 계약이 있다. W4 기존 payload에는 job_id가 없으므로 **어떤 인증된 서버 문맥으로 해당 Job에 연결할지**, W4 receipt/동일 version 충돌을 어떻게 표현할지 합의해야 한다. W4 메시지를 W3 worker에 보내거나 Job ID를 임의로 추정하지 않았다. 이 미확정 경계를 이번 실행기에서는 합성 저장 단계로 명시했다.

## CT-12 사전 검증과 공동 실행표

W1 CT-12 정본 runbook은 제공되지 않았다. 아래는 우리가 직접 실행한 로컬 검증과 남은 공동 검증을 구분한 표다.

| 시나리오 | 실제 결과 |
| --- | --- |
| W4 Core 메시지 → 최신 W1 envelope/payload schema | 통과 |
| W1 worker가 null question pin + UUID 회사 수집 명령 생성 | 통과, 새 row 저장은 합성 어댑터 |
| 실제 W1 relay 검사·JSON 직렬화 | 통과, SQS 송신 없음 |
| 실제 W1 private lookup이 동일 명령 반환 | 통과, TestClient+SQLite |
| 문항 변경·다른 회사/owner/입력·command 연결 변경 | SQL/route/runtime 검사에서 차단 |
| 잘못된 bearer/principal, 취소·삭제 epoch·fence 변경 | ASGI 조회에서 차단 |
| W4 동일 메시지 재시도·권한 철회 | 생성기에서 재시도 보존/철회 차단 |
| W4 inbound 영속 저장·dedup/충돌/ACK 유실 후 재시작 | **미구현 경계, 공동 검증 미실행** |
| PostgreSQL RLS·트랜잭션 원자성·동시성·W4/W1/W2 실제 queue | **미실행** |

최종 로컬 결과는 [local-integration.json](../output/question-core-integration-20260918/local-integration-final/local-integration.json)이다. `PASSED_LOCAL_PARTIAL`은 명시된 모의 경계를 포함한 부분 통합 성공이며 공동 CT-12 성공이 아니다. [Service 검사 기록](../output/question-core-integration-20260918/service-final.xml), [오프라인 생성 SQL](../output/question-core-integration-20260918/migration-offline.sql)도 보존했다. 앞선 focused 40개·중간 199개 기록은 당시 결과이며 최신 수치는 203개다.

## 재현

두 프로젝트 폴더를 같은 부모 아래 둔다. Service `backend/`에서:

```powershell
uv sync --locked --group dev
uv run python -m pytest tests/contract tests/runtime tests/test_health.py -q
uv run python ../../Project_EPICK_Engine/scripts/verify-question-core-integration.py --service-root .. --output-dir ../../Project_EPICK_Engine/output/question-core-recheck-new
```

실행기는 서비스 개발 의존성(pytest/SQLAlchemy 포함)을 사용한다. API 키·모델·팀 DB·queue는 필요 없다. 기존 출력 폴더 재사용은 거부한다. 공동 검증 전에는 W1 수정본 채택, P1~T5 회신, W4 수신 Job 매핑/저장·outbox 구현, 격리 PostgreSQL·queue와 정리 책임, 접근 가능한 CT-12 runbook/pin을 확보해야 한다.
