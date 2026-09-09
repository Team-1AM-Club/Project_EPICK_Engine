# W4 매칭 피드백 반영 결과

2026-09-09. 요청의 기업 근거 연결·서버 입력 경계·정책 재검사·제한 표시를 코드와 가상 통합 테스트에 반영했다.
현재 전체 테스트 **249개 통과**: 기존 216개 + 새 서비스/기업 계약 31개 + 원문 미보존 통신 검사 2개.
새 실제 모델 호출 0회. 두 HTTP 데모의 12회는 고정 응답 fixture를 호출한 모의 실행이다.
실제 팀 서비스 DB·인증·정책 서버 연동과 운영 모델 승인은 실행하지 않았다.
별도 전달용 폴더에 잠금 파일로 새 Python 3.13.12 환경을 설치한 뒤에도 전체 249개 테스트와 두 가상 HTTP 데모를 재현했다.
이번 기업 연결 프롬프트의 실제 LLM 의미 정확도는 새로 측정하지 않았다.

| 검토 요청 | 반영과 검증 |
|---|---|
| 기업 근거 ID를 입력·출력에 연결 | 서버 입력의 KnowledgeBundle 투영, Claim/Requirement·SourceVersion·Evidence 참조 검증, 후보별 실제 연결 근거 반환 |
| 수동 Claim·치환 자리 사용 금지 | 원본 진단 샘플을 정상 묶음으로 받지 않음. 제한 투영에는 manual_claim_examples를 복사하지 않음 |
| body owner_id를 권한으로 사용 금지 | 새 공개 입력은 project_id·문항 선택만 받음. owner/episodes/snapshot/모델 설정 추가 시 422 |
| 사용자 범위의 서버 조회 | load_context(user_id, project_id) 계약. 존재하지 않는 프로젝트와 권한 없는 프로젝트는 같은 404 |
| 호출 전/반환 전 상태 재검사 | 6회 모의 호출마다 PROCESS/SEND 확인, 반환 전 PROCESS/RETURN 확인. 도중 삭제·제외·동의 철회·W3 철회·원문 변경 시 차단 |
| 전문 오류·로그 복사 금지 | API 오류는 고정 코드만 반환. LocalClient capture_traces=False는 request/response 전문을 calls에 보존하지 않음. 성공·실패·예외 유출 검사 |
| 기업자료 한계 투영 | 원본의 게시일 미상·필수 첨부 미파싱을 결과에 보존. 해당 상태에서 기업 근거 사용 목록은 비어 있음 |
| 처리 상태·Job 구분 | processing_status로 반환. W1 상태 대응 제안 문서화, 합의 전 표시 유지 |
| 정렬 정책 승인 | 기존 순서 유지, 기업 연결을 가산점으로 추가하지 않음. PENDING_PRODUCT_REVIEW 표시 |

[실행 방법·스키마·함수 계약](w4-service-handoff.md)과 [가상 입력](../samples/service-handoff/request.json)을 기준으로 재현할 수 있다.
공개 요청·서버 입력·기업 묶음·출력의 JSON Schema 4개는 실행 시 쓰는 Pydantic 모델에서 생성하며 일치를 테스트한다.
교차 참조, 날짜 의미, 원문 위치, 접근 정책은 JSON Schema 밖에서 추가로 검사한다.

## 결과 해석

`synthetic-company.json`은 학습/적용을 보여 주는 가상 경험에 가상 기업 진술 1개와 우대 조건 1개를 연결한다.
VERIFIED/USABLE 표시는 검증된 입력을 받았다는 테스트 분기이며 실제 SK하이닉스의 검증 결과가 아니다.
`diagnostic-company.json`은 기업 근거를 사용하지 않고 SourceReview를 전달한다. 경험의 문항 부합은 제한 상태로 반환한다.
두 결과의 모델명은 simulated-*이며, 이번 통합 검증 결과를 새 모델 성능 점수로 합산하면 안 된다.

## 남은 합의·실연동

- W3: `w3-w4-projection/0.1-draft` 필드·상태 의미와 실제 W3 계약 대응. 기존 ALLOWED를 USABLE로 자동 치환하지 않음.
- Backend/W1: 실제 사용자 범위 조회, 리비전 일관성, 동의·삭제·전송·반환 정책 구현과 테스트 서버 검증.
- W1: COMPLETED_WITH_LIMITATIONS와 공통 Job PARTIALLY_COMPLETED 등의 대응 승인.
- PO/W4: 근거 종류 수를 사용하는 정렬 정책 승인.
- 모델 품질: 이전 v4의 필수 검사 실패와 사람의 정답 검토 미완료를 해소한 뒤 운영 모델 선정.

별도로 확보·시각 검토한 JD PDF는 [9월 8일 기록](skhynix-source-verification-2026-09-08.md)에 있다.
이를 원래 W3 샘플과 같은 버전의 운영 검증 결과로 간주하지 않았으며, 새 W3 ID·근거·상태로 연결하는 작업은 남아 있다.
