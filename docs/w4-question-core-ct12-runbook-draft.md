# W1–W4 공동 CT-12 준비표

상태: **DRAFT / NOT_RUN**. [W1 요청서 D09](inputs/W1_W4_Required_Contracts_2026-09-19.md)에 따른 준비 문서다.
로컬 SQLite·모의 queue 결과를 공동 CT-12로 기입하지 않는다.

[최신 runtime 회신과 queue 준비 선후관계](w4-actual-runtime-handoff-reply-2026-09-19.md)를 함께 확인한다.

## 실행 전 준비

| 필요 항목 | 상태 | 담당 |
| --- | --- | --- |
| D01 계약·P1–P3 정책·T1–T5 책임 합의 | 대기 | W1/W4·정책 승인자 |
| 후보 원문·합의 schema/fixture/digest·양측 full SHA | W1 519b9127 wire 채택 원본7개·W4 호환 검증 완료. W4 공유 commit 및 runtime 설정 대기 | W1/W4 |
| W1 인증 context 전달·갱신·철회 규칙 | 미확정 | W1 제공/W4 adapter |
| 합성 자료·W1 기대 row count 조회 명령 | 미제공 | W1/W4 |
| W4 영속 volume·producer image digest | 미제공 | W4·환경 제공 측 |
| 격리 PostgreSQL/SQS·W4 send-only·W1 consumer principal | W1 기본 설정 완료 보고. 실제 W4 연결 identity·queue 정보와 공동 실측은 대기 | 환경 제공 측 |
| W1 commit/delete·취소/삭제 주입·user retry·W2 lookup 명령 | 미제공 | W1/W2 |
| teardown 담당·리소스 식별자·공용 Source 보존 기준 | 미합의 | W1/W4/W2 |

운영 자료·운영 환경을 사용하지 않는다. 비밀값 대신 설정 이름을 기록한다.
W4 동작 중인 DB는 Google Drive로 공유하지 않고 단일 host의 영속 로컬 volume에 둔다.
담당자 실명과 일정은 팀에서 확정한다.

## 10개 시나리오

환경별 주입·조회 명령은 아직 없어 실행 가능한 명령으로 제시하지 않는다.
각 행에 고정 SHA·실제 명령·결과·row count·증거 경로를 채운다.

| ID | 실행 | 확인할 결과 | 실행 책임 | 상태 |
| --- | --- | --- | --- | --- |
| CT12-01 | 합성 Core/Non-Core 준비·발행 | schema·Job 결속 일치, W1 올바른 적용. 수신만으로 W2 실행 없음 | W4/W1 | NOT_RUN |
| CT12-02 | 동일 메시지 10회 이상 전달 | ID/body/digest 불변, 논리적 적용 1회. receipt/decision/binding row count는 채택 consumer 기준으로 확정 | W4/W1 | NOT_RUN |
| CT12-03 | 같은 ID/다른 body·같은 revision 충돌·같은 decision ID/다른 message 주입 | 기존 결정 덮어쓰기 없이 합의된 거부. 비정상 메시지 주입은 격리 consumer 검사에 한정 | W1/W4 | NOT_RUN |
| CT12-04 | stale input/revision·잘못된 principal | W4 currentness 차단과 W1 인증·현재성 차단을 각각 확인 | W4/W1 | NOT_RUN |
| CT12-05 | W4 commit 후 종료·재시작·응답 유실 | 영속 row 복구, 같은 ID/body 재전송, acceptance 전 sent 전환 없음 | W4 | NOT_RUN |
| CT12-06 | W1 DB commit 뒤 queue delete 전 재시작 | 재수신해도 논리적 재적용·중복 실행 없음 | W1 | NOT_RUN |
| CT12-07 | W1 확정 전후 취소·owner 삭제 | fence/epoch 규칙에 따른 stale 적용·노출 차단 | W1, W4 협조 | NOT_RUN |
| CT12-08 | receipt 이후 사용자 retry 없이 관찰 | 새 W2 command 0건 | W1/W2 | NOT_RUN |
| CT12-09 | 명시적 사용자 retry | 새 fence와 승인된 W2 command, relay·protected lookup 결속 확인 | W1/W2 | NOT_RUN |
| CT12-10 | 관계 변경 후 relay/lookup·owner 삭제 | 변경 반영·접근 차단, 다른 owner의 공용 Source 보존 | W1/W2, W4 협조 | NOT_RUN |

## 실행 증거 양식

- run_id, UTC 시작·종료 시각, 실행 담당자.
- W1/W4/W2 full SHA, 채택 schema·fixture manifest SHA-256, policy 승인 기록.
- 실제 producer immutable image digest, 격리 DB/queue 식별자, principal·최소 권한 검사.
- CT12 ID별 명령, expected/actual, row count, 증거 경로, PASS/FAIL.
- 실제 SendMessage·W1 logical apply·W2 command 횟수.
- 종료·응답 유실·취소·삭제 주입 위치와 관측 결과.
- teardown 담당·완료 시각·잔존 리소스·공용 Source 보존 결과.

10개 시나리오와 teardown까지 통과한 뒤에만 공동 완료를 검토한다.
준비표의 작성은 환경 준비나 실행 완료를 뜻하지 않는다.
