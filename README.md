# Project EPICK Agent Engine

> 공식 Source를 수집하고, 검증 가능한 Evidence와 이력을 남겨 EPICK의 지식·추천 파이프라인에 안전하게 전달하는 Agent Engine입니다.

## 📋 프로젝트 소개

EPICK Agent Engine은 공고·웹사이트·공식 API 등 승인된 공식 Source를 수집하여 `SourceVersion`, `Evidence`, 수집 결과를 PostgreSQL에 보존합니다. 이 저장소는 현재 **W2 Source Collection** 구현의 기준 저장소입니다.

W3의 지식 색인·restriction 처리와 W4의 근거 기반 추천은 전체 EPICK 흐름에 포함되지만, 각각 별도 Workstream이 소유합니다. 따라서 이 README는 세 기능의 책임과 연동 조건을 함께 설명하되, 아직 확정되지 않은 계약이나 운영 배포를 완료된 기능으로 표현하지 않습니다.

## 🧑‍💻 Team

<table>
  <tr>
    <td align="center" width="160px">
      <a href="https://github.com/romain1121">
        <img src="https://github.com/romain1121.png" width="80" alt="romain1121" /><br />
        <strong>romain1121</strong><br />
        <img src="https://img.shields.io/badge/W2-Source%20%26%20Collection-2E8B57?style=flat&amp;logoColor=white" alt="W2 Source Collection" />
      </a>
    </td>
    <td align="center" width="160px">
      <a href="https://github.com/FreeRease">
        <img src="https://github.com/FreeRease.png" width="80" alt="FreeRease" /><br />
        <strong>FreeRease</strong><br />
        <img src="https://img.shields.io/badge/W4-Recommendation-6A5ACD?style=flat&amp;logoColor=white" alt="W4 Recommendation" />
      </a>
    </td>
  </tr>
</table>

## 🎯 제공 기능

- 승인된 공식 Source의 등록, 수집, 파싱 및 증거 추출
- SourceVersion·Evidence·outbox의 원자적 영속화와 provenance 보존
- 정적 공식 채용공고부터 시작하는 수집 정책 및 파서 검증
- source revision, 수집 실패, 재시도 permit, fence·deletion epoch를 고려한 복구 테스트
- FastAPI 경계, SQLAlchemy/Alembic 기반 PostgreSQL 저장소, Scrapy 수집기

## 🧭 W2 · W3 · W4 협업 구조

```mermaid
flowchart LR
    W1[W1 Platform\nprivate Job / fence / deletion epoch]
    W2[W2 Engine\nofficial Source collection]
    DB[(PostgreSQL\nSourceVersion / Evidence / Outbox)]
    W3[W3 Knowledge\nrestriction / indexing]
    W4[W4 Recommendation\nmatching / details]

    W1 -->|private collection command| W2
    W2 --> DB
    W2 -->|private result| W1
    W2 -. approved versioned adapter, ACK Gate .-> W3
    W3 -. indexed or restricted usability Gate .-> W4
    W4 -. private candidate result Gate .-> W1
```

| Workstream | 소유 책임                                                                      | 이 저장소에서의 상태                       |
| ---------- | ------------------------------------------------------------------------------ | ------------------------------------------ |
| W2         | 공식 Source 수집, SourceVersion·Evidence·outbox 영속화                         | 구현·테스트 대상                           |
| W3         | Claim/Requirement 해석, knowledge indexing, restriction 상태                   | 별도 구현; 후보 계약 및 채택 Gate 존재     |
| W4         | 근거·제약을 반영한 질문 후보와 추천                                            | 별도 구현; 실운영 연동 Gate 존재           |
| W1         | 인증 principal, private Job/Checkpoint, dispatch, queue, fence, deletion epoch | 플랫폼 권위자; Engine이 중복 구현하지 않음 |

W2의 수집 성공은 W3의 검증·색인 완료를 뜻하지 않으며, W4는 W3가 `INDEXED` 또는 명시적 `RESTRICTED` 상태를 확정하기 전에는 추천을 시작할 수 없습니다.

## 🔐 계약과 데이터 경계

- 공용 event의 바깥 transport envelope는 W1이 소유하며 outer `schema_version`은 `"1.0"`입니다.
- W2의 공용 domain payload는 `schema_version: "w2.source.v1"`으로 선택합니다. event ID·revision 등 transport 필드는 payload에 중복하지 않습니다.
- 공용 계약의 정본 경로는 Service 저장소의 `backend/contracts/common/v1/event-envelope.schema.json`, `backend/contracts/w2/v1/`, `backend/contracts/fixtures/v1/w2/`입니다. Engine 저장소에 이를 복제하지 않습니다.
- 기존 `v0.2 SourceEvent`를 새 envelope payload로 그대로 중첩하거나 덮어쓰지 않습니다.
- W3의 `w3-restriction/0.1-draft`는 로컬 검증용 **후보 계약**입니다. W2와 wire-compatible하다고 확정되지 않았으므로, 승인된 versioned adapter·consumer·ACK가 준비되기 전 W2가 직접 publish하거나 W3가 직접 consume하지 않습니다.
- W4의 public input에는 owner/user, private Job·Checkpoint correlation, 원문 Source body, credential, model key를 넣지 않습니다. 민감한 private lifecycle은 W1 경계에서 관리합니다.

## 🛠️ 기술 스택

| 영역             | 구성                                     |
| ---------------- | ---------------------------------------- |
| Language         | Python 3.12                              |
| API · Validation | FastAPI, Pydantic                        |
| Collection       | Scrapy                                   |
| Persistence      | PostgreSQL, SQLAlchemy, Alembic, Psycopg |
| Verification     | pytest, Ruff, mypy                       |
| Local database   | Docker Compose (`compose.test.yaml`)     |

### W3 · Knowledge & Restriction

![Python](https://img.shields.io/badge/Python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![FTS5](https://img.shields.io/badge/SQLite%20FTS5-003B57?style=for-the-badge&logo=sqlite&logoColor=white)

W3는 source restriction 상태와 knowledge indexing을 담당하며, SQLite/FTS5 기반의 로컬 색인·replay/snapshot recovery 경계를 보유합니다. 공용 연동은 후보 계약 검증 단계이므로 이 스택은 W3의 로컬 구현 기준입니다.

### W4 · Recommendation

![Python](https://img.shields.io/badge/Python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)

W4는 safe HTTP router, input validation, contract fixture 검증을 기반으로 추천 경계를 구현합니다. 실제 provider 호출과 운영 데이터 연동은 별도 Gate이며, badge는 현재 확인된 W4 구현 범위만 나타냅니다.

## 📁 프로젝트 구조

```text
Project_EPICK_Engine/
├── src/epick_engine/source_collection/
│   ├── api.py             # Source Collection API boundary
│   ├── collector.py       # 공식 Source 수집기
│   ├── parsing.py         # 공고·증거 파싱
│   ├── persistence.py     # SourceVersion/Evidence/outbox 저장
│   ├── policy.py          # 승인 Source 및 수집 정책
│   ├── service.py         # 수집 orchestration
│   └── worker.py          # W1 command 경계용 worker 구성
├── alembic/               # PostgreSQL migration
├── tests/
│   ├── unit/source_collection/
│   ├── contract/
│   └── integration/source_collection/
├── compose.test.yaml
└── pyproject.toml
```

## 🚀 로컬 개발 시작하기

### 사전 요구 사항

- Python 3.12
- Docker Desktop 또는 Docker Engine + Compose
- `uv` 권장

### 설치 및 테스트 DB 실행

```powershell
cd Project_EPICK_Engine
uv sync --all-groups
rtk proxy docker compose -f compose.test.yaml up -d --wait
```

`rtk`는 개발 환경의 선택적 proxy입니다. 사용할 수 없다면 명령 앞의 `rtk proxy`를 제외하고 실행합니다.

### migration 적용

```powershell
$env:EPICK_DATABASE_URL = 'postgresql+psycopg://epick_test@127.0.0.1:55439/epick_test'
rtk proxy .\.venv\Scripts\python.exe -m alembic upgrade head
rtk proxy .\.venv\Scripts\python.exe -m alembic current
Remove-Item Env:EPICK_DATABASE_URL -ErrorAction SilentlyContinue
```

### 검증 실행

```powershell
$env:EPICK_TEST_DATABASE_URL = 'postgresql+psycopg://epick_test@127.0.0.1:55439/epick_test'
$env:EPICK_TEST_DATABASE_APPROVED = '1'
rtk proxy .\.venv\Scripts\python.exe -m pytest tests/unit/source_collection tests/contract tests/integration/source_collection
rtk proxy .\.venv\Scripts\python.exe -m ruff check src tests
rtk proxy .\.venv\Scripts\python.exe -m mypy src
rtk proxy docker compose -f compose.test.yaml down
```

현재 이 저장소에는 독립 실행 가능한 `epick_engine.app:app` 또는 Celery runtime entrypoint가 없습니다. Uvicorn·Celery 실행은 W1의 Platform authority, private Job lifecycle, Linux 통합 환경이 제공된 뒤의 Gate이며, 작동하는 명령처럼 문서화하지 않습니다.

## 🧪 검증 원칙

- 네트워크 fetch·파싱은 DB transaction 밖에서 수행합니다.
- SourceVersion·Evidence·outbox만 짧은 transaction에서 함께 기록합니다.
- 재시도는 새 permit과 현재 fence·deletion epoch를 확인하며, 이전 성공 결과를 잘못 재사용하지 않습니다.
- 공식 개별 채용공고에서 검증된 H1은 `job_title`로 인정하되, provenance와 evidence를 함께 남깁니다.
- 수집 실패, atomic persistence, outbox, retention origin, recovery fault를 unit·contract·integration 테스트로 검증합니다.

## 🛡️ 데이터 안전과 보존

- 공용 event와 fixture에는 개인 식별자, Job/Project/Checkpoint correlation, 원문 본문, secret을 포함하지 않습니다.
- W3 restriction이 발생하면 새 knowledge 사용을 중지하고 색인 결과를 제거하거나 무효화해야 합니다. 재색인 완료 전 usability를 복원하지 않습니다.
- W4는 VERIFIED + USABLE evidence와 명시적 requirement만 사용하며, 누락된 evidence로 eligibility를 추론하지 않습니다.
- 동의·삭제·철회와 context version은 모델 호출과 결과 반환 직전에 다시 확인해야 합니다.

## 📚 참고 문서

- W2 계획·작업·검증: `../specs/001-official-source-collection/`
- 공식 Source 후보: `../.agents/docs/02_OFFICIAL_SOURCE_CANDIDATES.md`
- W3 restriction handoff: `../.agents/docs/EPICK_W3_Restriction_Handoff_2026-09-13/w3-restriction-handoff.md`
- W4 service handoff: `../.agents/docs/reply_260915/w4-service-handoff.md`
- 공용 계약 정본: [Project_EPICK_Service `backend/contracts/README.md`](https://github.com/Team-1AM-Club/Project_EPICK_Service/blob/develop/backend/contracts/README.md)

## 🤝 기여 원칙

변경 전에는 승인 Source·계약 정본·workstream 책임을 확인합니다. 공용 schema, fixture, public event를 바꾸는 경우 W1 envelope 및 W2/W3/W4 consumer 영향까지 함께 검토해야 합니다. 개인 데이터·secret·원문 body를 새 로그나 계약에 추가하지 마십시오.
