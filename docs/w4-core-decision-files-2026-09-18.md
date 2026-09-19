# W4 Core Decision 전달 파일 안내

**W1 담당자에게는 회신 초안과 ZIP을 함께 전달하면 된다.** 먼저 [W1 회신 초안](w4-core-decision-reply-2026-09-18.md)을 검토하고, 구현 검토 시 [계약·검증·실행법](w4-core-decision-contract-2026-09-18.md)을 따른다. 외부 발송은 아직 하지 않았다.

| 파일 | 기능 |
| --- | --- |
| `epick_w4/core_decision.py` | W4 Core Decision 메시지 생성, owner·입력·버전 재검사, W1 receipt 검사. 실제 전송 없음 |
| `epick_w4/core_decision_schemas/envelope.schema.json` | private envelope의 producer·channel·ID·시각 형식 |
| `epick_w4/core_decision_schemas/payload.schema.json` | Core 결정 대상·버전·필수 여부 형식 |
| `epick_w4/core_decision_schemas/receipt.schema.json` | W1 수신 결과 6종 형식. W2 gate ACK와 다름 |
| `epick_w4/core_decision_schemas/baseline.json` | 기존 Service commit, 원본 경로, 8개 고정 파일의 SHA-256 |
| `samples/core-decision/context.json`, `context.schema.json` | 합성 서버 문맥과 W4 로컬 스키마 제안. 외부 전송 payload 아님 |
| `samples/core-decision/core-required.json`, `non-core.json` | 필수/보조 Source 정상 메시지 |
| `samples/core-decision/negative-messages.json` | scope·company·버전·원문 추가 등 20가지 거부 사례와 예상 오류 |
| `samples/core-decision/receipts.json` | 수신 결과 6종의 합성 예시 |
| `samples/core-decision/upstream/` | 변경하지 않은 W1 기준 fixture·README·검사 코드와 W2 command schema. 참고·재현용이며 운영 W1을 수정하는 파일이 아님 |
| `examples/w4_core_decision_demo.py` | 정상·거부·receipt·재시도 시연과 회사 결속 충돌 재현 |
| `scripts/demo-core-decision.py` | 새 출력 폴더에 위 시연 결과 저장 |
| `scripts/prepare-core-decision-fixtures.py` | 명시된 합성 fixture 재생성. 모델·네트워크 호출 없음 |
| `scripts/prepare-core-decision-pin.py` | 이 PC의 별도 Service Git clone에서 지정 commit 원본 바이트를 가져오는 유지보수 도구. 일반 시연에는 실행할 필요 없음 |
| `tests/test_core_decision.py` | 새 경계 테스트 30개. 회사 충돌이 해소됐다고 오인하지 않도록 재현 결과 검사 |
| `output/core-decision-20260918/demo/core-decision-demo.json` | 이번 실제 오프라인 시연 결과. `PASSED`는 로컬 검사 결과 |
| `output/core-decision-20260918/verification/` | 전체 테스트 381개·가상 HTTP 시연 2개 결과, 실행 환경, 검사 당시 소스 해시·로그 |

ZIP에는 위 파일과 실행에 필요한 기존 Python 패키지·테스트·합성 샘플·잠금 의존성도 포함한다. `api.py`는 기존 추천 HTTP 진입점이며 새 Core Decision을 자동 발행하지 않는다. 새 모듈 하나만 떼면 공통 계약 타입과 의존 패키지가 빠지므로 동봉 소스 기준으로 검토한다.

`MANIFEST.json`은 ZIP 내 파일의 SHA-256, `SOURCE-STATE.json`은 미커밋 작업 트리에서 만든 전달본이라는 상태를 기록한다. Git checkout·병합·배포용 완료 commit이 아니다. 모델 가중치, 가상환경, DB, Git 인증정보는 포함하지 않는다. 이전 단계의 큰 모델 추론 결과는 기존 `EPICK_W4_Staged_W1_Handoff_2026-09-18.zip`에 보존돼 있으며 이번 ZIP은 Core Decision 검토를 위한 별도 전달본이다. 과거 문서의 output 링크는 이전 전달본을 가리킬 수 있다.

남은 작업: W1 회사 결속 수정, Core 판단 정책·version/outbox/전송 책임 합의, 접근 가능한 W4 구현 pin, 실제 격리 환경과 공동 CT-12. 로컬 가상 검증만으로 완료 처리하지 않는다.
