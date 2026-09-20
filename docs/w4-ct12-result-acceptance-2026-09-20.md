# W4 → W1 실제 CT-12 결과 수용·Compose 보정 회신 · 2026-09-20 r6

상태: **W1 actual W4→W1 CT-12 PASS 보고 수용 / W4 Compose 후속 검증 / W2 확인·teardown 대기**.
이 문서는 r5의 실제 환경 미실행·C1 수정 대기 상태를 갱신한다. 새 API/event/계약은 추가하지 않는다.

## 1. 실제 실행 기준과 검증 범위

| 항목 | 수용한 실제 실행 기준 | W4 확인 범위 |
| --- | --- | --- |
| W1 source | `08f03594201bb972089b12d9998d3518098e903b` | Git 원본 조회 |
| W1 C1 fix | `a9ae27b48340040aa815b9a3062ab8e02a3a9812` | 실제 실행 source의 ancestor 및 owner epoch 비교·DB 회귀 테스트 추가 확인 |
| W1 image | `sha256:089e6bdfca7723a0dcef2c959da326ef6c09cadb4ef87a901d5198cc3653dca6` | W1 실행 보고의 pin 수용, registry 직접 조회 안 함 |
| W4 actual-run source | `df41433218918e4167784243dc9b88e5a858278d` | 앞서 W4가 push한 r5 source와 일치 |
| W4 actual-run ECR image | `sha256:6242659913adec077299897433c3023e7d42b49898fc266b41d1c3355d740e7d` | W1 실행 보고의 pin 수용, registry 직접 조회 안 함 |

W1 원본에서 `owner["deletion_epoch"] != context.owner_deletion_epoch`와
owner epoch만 증가시킨 뒤 첫 resolve가 false/revoked인지 검사하는 DB 테스트를 확인했다.
**C1 구현 누락은 해결된 것으로 수용한다.** W4가 그 DB 테스트나 실제 AWS 시나리오를 재실행하지는 않았다.

Schema는 기존 bytes와 SHA-256이 동일하다:
`1d004ea5ea4bbd346926c6be878de759f25b43011b7117ff8700c4d48e8b71af`.
결과 문서 §2의 schema 경로는 표기 정정이 필요하다. 고정 commit에 실제 존재하는 경로는
`backend/contracts/w4/v1/question-core-decision.event.schema.json`이며,
`w4-question-core-decision.event.schema.json`은 그 경로에 없다. 새로운 wire 변경은 아니다.

## 2. 결과 수용

W1의 [실행 보고 원문](inputs/W1_W4_CT12_Actual_Runtime_Result_2026-09-20.md)을 근거로 다음을 수용한다.

- 정상 적용 1회와 동일 body의 duplicate 처리; 추가 decision/binding/command 없음.
- W1 commit 이후 응답 유실 시 늦은 재전송 차단; sent outbox 재시작 시 IDLE.
- prepare 이후 취소·owner epoch·Job–Source 결속 변경 시 send 전 차단, W1 영속 행 모두 0.
- receipt만으로 W2 command를 만들지 않음; 명시적 retry 후에만 command/outbox 각각 1건.
- W1 별도 격리 suite의 malformed/principal/DB failure/ACK loss 처리 결과.

이 상태는 **W1_EXECUTION_REPORT_ACCEPTED**다. W1 호스트의 `/opt/epick/ct12/evidence` 및
`w1-w4-ct12-evidence-20260920.tar.gz` 원본은 W4가 받거나 직접 hash 검증하지 않았다.
보고된 archive hash `23d3fd3b85d3d2463050bcbf575900f7cb72d2f9463ccf72b15aac9f88f25bcc`와
6개 JSON hash는 W1 보고값이며, W4 독립 검증값으로 표시하지 않는다.
이 자료가 추후 전달되면 동일 run의 증거로 대조할 수 있다.

## 3. W4 Compose 보정

`deploy/question-core/compose.yaml`의 tmpfs를 하나의 문자열로 묶었다.

```yaml
tmpfs: ["/tmp:rw,noexec,nosuid,nodev,size=16m"]
```

이전 flow sequence에서는 쉼표 뒤 옵션들이 별도 list item으로 해석되어 잘못된 mount 경로가 됐다.
기존 CI는 `docker run --tmpfs ...`로 검사해 실제 Compose를 거치지 않았고, 그래서 결함을 놓쳤다.
후속 CI는 저장소의 실제 Compose 파일을 파싱하고 Linux에서 `docker compose run ... check`를 두 번 실행한다.
같은 harness에서 보정 전 표현이 mount 오류로 실패하는 것도 확인하도록 추가했다.

CI만 외부 registry 대신 빌드된 immutable local image ID를 사용한다. override는 ECR reference
메타데이터 환경변수 제거와 CI 전용 network/volume 이름에 한정한다. tmpfs·UID·read-only·mount·entrypoint는
원본 Compose에서 가져온다. [Compose override의 reset 동작](https://docs.docker.com/reference/compose-file/merge/#reset-value)을 사용한다.
CI는 실제 W1/AWS를 호출하지 않고 합성 설정으로 기동만 검사한다. W1 staging teardown과도 별개다.

후속 source의 full SHA와 CI 실행 결과는 전달본의 `W4-FOLLOWUP-SOURCE.json`에 기록한다.
실제 CT-12에서 사용한 r5 source/image pin을 이 후속 SHA로 소급 변경하지 않는다.
이 보정은 W1이 호스트 복사본에 이미 적용한 수정과 같고, Python producer/relay 코드는 바꾸지 않았다.

## 4. REAL·W2·teardown

- REAL 사용자 자료 발행: **DISABLED**. P2/P3 policy owner/revision 승인 전 유지.
- W2의 같은 run command protected lookup/actual receipt: **PENDING**.
  기존 W1–W2 protected lookup/commit-gate 계약으로 확인한다. W4 신규 API/event는 필요 없다.
- CT-12 teardown: **PENDING**. W1/W2가 증거 보존을 확인한 뒤 임시 credential/container/DB/AWS 자원 정리 기록을 남긴다.
  W4는 원격 자원을 직접 삭제하지 않았다. CI의 임시 fixture 정리는 staging teardown 증거가 아니다.

W4 후속 Compose 검증까지 완료해 회신한 뒤에는 **W2 확인과 staging teardown 기록**이 종료 조건으로 남는다.
그 전에는 `W1_W4_COMPLETE`, W2 최종 소비 완료 또는 REAL enablement를 선언하지 않는다.
