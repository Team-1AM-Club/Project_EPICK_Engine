# W4 필수 r3 회신 전달 안내 · 2026-09-19 r3.1

이 문서는 당시 전달 기록이다. 현재 후속은 [runtime 준비 전달 안내 r4](w4-actual-runtime-handoff-guide-2026-09-19.md)다.

**전달 대상은 `EPICK_W4_Mandatory_R3_Reply_2026-09-19_r3.1.zip`이다.**
[필수 A–F 회신](w4-mandatory-r3-reply-2026-09-19.md)을 먼저 읽는다. W1에 실제 발송하지 않은 W4 회신 초안이다.
W1의 이번 요청은 원문 미수령 상태였던 r2를 기준으로 한다. 직전 r3에서 확보한 후보 원문·수정 코드·검증 증거를 유지하면서 지정한 필수 양식을 채웠다.

## 이번 보완

| 요구 | 회신 |
| --- | --- |
| A 원문 수령 | 후보2개 각각 계산 SHA-256·제공 SHA-256 일치, byte_verified=true |
| B D01-01~08 | 8개 모두 W4 기술적 채택, 항목별 코드·테스트 경로와 실제 연결 blocker 기록 |
| C P1~P3 | P1 기술적 채택, P2/P3 운영 승인 보류. 정책 승인 owner는 PENDING, W4 책임·해제 조건 명시 |
| D T1~T5 | 5개 책임 경계를 W4 입장으로 수용. 상대 팀 확인 담당과 미확인 사항 명시 |
| E 구현·인계 | 8개 영역의 로컬 구현/검증과 실제 adapter·공유 commit·image·공동 CT-12 미완료를 분리 |
| F 후속 artifact | full SHA·adopted schema/fixture·migration 설명·image·sender identity·공동 실행/정리 책임의 제공 조건 명시 |

W1은 이 자료를 검토해 계약 채택 구현 입력의 준비 여부를 판단한다. W4는 이를 대신 승인하지 않는다.
양식 기입 완료가 양측 계약 채택·운영 준비·AWS 권한 부여·공동 CT-12 완료를 뜻하지 않는다.

## 파일별 역할

| 파일 | 역할 |
| --- | --- |
| [필수 회신 r3.1](w4-mandatory-r3-reply-2026-09-19.md) | W1 §4 text 블록 전체를 채운 제출용 문서 |
| [이번 W1 요청 원본](inputs/W1_W4_Mandatory_R3_Reply_Format_2026-09-19.md) | 필수 형식·수락 기준 원본 사본 |
| [직전 r3 상세 검토](w4-required-contracts-reply-2026-09-19-r3.md) | type:null codec 수정·schema와 정책의 차이·fixture 상세 근거 |
| [직전 파일 안내](w4-question-core-candidate-handoff-2026-09-19.md) | producer/outbox/relay·fixture·검증 스크립트별 기능 |
| [후보 전달서](inputs/W1_W4_Candidate_Contract_Source_2026-09-19.md) / [출처·hash](../samples/question-core-candidate-20260919/source-provenance.json) | 추출 원문2개의 byte 수령 및 제공 hash 대조 근거 |
| [codec](../epick_w4/question_core_contract.py), [producer](../epick_w4/question_core_producer.py), [outbox](../epick_w4/question_core_outbox.py), [relay](../epick_w4/question_core_relay.py) | 직전 r3와 같은 실제 로컬 구현. 이번 runtime 변경 없음 |
| [관련73개·복구 증거](../output/question-core-candidate-20260919/local/summary.json) / [전체454개·가상 HTTP 결과](../output/question-core-candidate-20260919/full/summary.json) | 직전 실제 로컬 실행 결과. 이번 재실행 아님 |
| [host 실행 안내](w4-question-core-producer.md) / [CT-12 준비표](w4-question-core-ct12-runbook-draft.md) | 실제 context/policy adapter·영속 volume·identity의 남은 조건, 공동 검증 시나리오 |
| ZIP 루트 `REPLY-FORMAT-VERIFICATION.json` | 요청 원본 hash, 필수 항목·참조 경로 검사, 직전 검증 source 219개씩의 현재 hash 대조 결과 |
| ZIP 루트 `SOURCE-STATE.json` / `MANIFEST.json` | 현재 미완료 상태 및 패키지 전체 파일별 hash |

ZIP에는 import 의존 코드·샘플·스키마·테스트·잠금 파일·기존 검증 증거를 포함한다.
운영 secret/token·모델 가중치·가상환경·Git metadata·실행 DB는 포함하지 않는다.
안전한 설정 변수명은 host wiring용 제안이며 실제 값이나 배포 CLI 제공을 의미하지 않는다.

## 검증 경계와 다음 단계

이번에는 회신 문서와 전달 패키지를 보완했다. source manifest에 기록된 파일219개를 직전 관련/전체 검사 기록 각각과 대조했고 모두 일치했다. 새 런타임 테스트는 실행하지 않았다.
73개와454개는 서로 중복을 포함한 별도 검사 결과이므로 합산하지 않는다. 원격 CI·실제 SQS·W1 context·공동 CT-12를 실행하지 않았다.
기존 r3 ZIP의 byte는 보존하고, 새 ZIP에는 필수 양식과 최신 진입 문서를 포함한다. ZIP은 접근 가능한 producer commit SHA를 대신하지 않는다.

1. W1에서 D01–D03 항목별 수용·이견 회신, 팀에서 정책 승인 owner 지정 및 P2/P3 검토·승인.
2. 합의한 version/schema·body 상한·digest/fixture·codec 반영 및 검증 후 양측 commit/push·full SHA 교환.
3. 실제 W1 인증 context와 W4 정책 adapter, producer image·영속 volume·격리 queue·sender identity 준비.
4. W1/W4/W2가 공동 CT-12를 실행하고 결과·teardown 증거 확인.

## W1에 전달할 문안

> 요청한 필수 r3 A–F 형식으로 보완한 r3.1 회신과 구현·검증 자료를 첨부합니다.
> 후보 원문2개는 제공 SHA-256과 일치하며 D01 8개 항목을 W4 기술적 채택으로 회신합니다.
> 정책 승인 owner·P2/P3 운영 승인, 접근 가능한 producer commit, 실제 adapter/image/queue·공동 CT-12는 PENDING 또는 NOT_RUN으로 명시했습니다.
> D01–D03의 수용·이견과 정책 승인 담당 지정을 확인 부탁드립니다. 이번 자료는 양측 합의나 실제 연결 완료를 선언한 것이 아닙니다.

미발송 초안이다. 실제 role ARN/SenderId는 양측 합의와 격리 queue 준비 뒤 안전 채널로 제공한다.
