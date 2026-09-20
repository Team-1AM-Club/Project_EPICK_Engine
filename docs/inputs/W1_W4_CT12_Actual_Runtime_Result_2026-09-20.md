# W1 → W4 Question Core 공동 CT-12 실제 Runtime 결과

작성일: 2026-09-20  
송신: W1  
수신: W4  
실행 범위: 합성 데이터 전용 W1–W4 Question Core CT-12  
현재 판정: **`ACTUAL_W4_TO_W1_CT12_PASSED / W2_DOWNSTREAM_CONFIRMATION_AND_TEARDOWN_PENDING`**

## 1. 결론

W4의 실제 producer·durable SQLite outbox·send-only relay를 고정 image digest로
기동하고, AWS의 CT-12 전용 SQS를 통해 W1 consumer에 전달했다. W1은 격리
PostgreSQL에서 정상 적용, 동일 본문 재전송, 응답 유실, 재시작, 명시적 retry,
취소, owner deletion epoch 증가, Job–Source 관계 변경을 검증했다.

검증 결과는 다음과 같다.

- 정상 W4 event는 W1에 **한 번만** 적용됐다.
- 동일 message/body의 재전송은 `duplicate`로 완료되고 새 decision·binding·command를
  만들지 않았다.
- W1 적용 후 W4 relay 응답 유실을 재현해도 늦은 재전송은
  `CORE_CONTEXT_NOT_CURRENT`로 차단됐다.
- Core 판단 수신만으로 W2 command를 만들지 않았고, W1 명시적 retry 후에만
  `JobCommand=1`, `OutboxMessage=1`이 생성됐다.
- W4 prepare 후에 Job 취소, owner deletion epoch 증가, Job–Source 관계 변경을
  각각 주입했을 때 relay는 SQS 전송 전에 차단됐다.
- 차단 시나리오의 W1 DB 결과는 receipt·decision·binding·command·outbox 모두
  `0`이었다.
- 실행 후 CT-12 Main Queue와 DLQ의 visible·in-flight·delayed message는 모두 `0`이었다.

따라서 **W4 실제 producer → SQS → W1 consumer의 Question Core 경계와 늦은 개인
쓰기 차단은 통과**했다. 다만 이 문서는 다음 두 항목을 아직 완료로 선언하지
않는다.

1. 같은 actual W4 run에서 생성된 command를 W2가 protected lookup으로 읽고 수신했다는
   W2 담당 확인
2. CT-12 임시 credential·container·DB·AWS 자원의 합의된 teardown

## 2. 고정 artifact

| 항목 | 고정값 | 판정 |
| --- | --- | --- |
| W1 source | `08f03594201bb972089b12d9998d3518098e903b` | `develop`/`origin/develop` 일치 |
| W1 owner epoch fence | `a9ae27b48340040aa815b9a3062ab8e02a3a9812` | W4 지적 C1 보완 커밋 |
| W1 image | `sha256:089e6bdfca7723a0dcef2c959da326ef6c09cadb4ef87a901d5198cc3653dca6` | digest pin으로 실행 |
| W4 source | `df41433218918e4167784243dc9b88e5a858278d` | 전달 branch HEAD와 일치 |
| W4 image | `sha256:6242659913adec077299897433c3023e7d42b49898fc266b41d1c3355d740e7d` | W4 전용 ECR digest pin으로 실행 |
| W1 adopted schema | `backend/contracts/w4/v1/w4-question-core-decision.event.schema.json` | W1 parser/consumer가 사용 |
| W1 context interface | `backend/app/runtime/w4_question_core_context.py` | prepare/send/restart 현재성 판정 |
| W1 inbound transaction | `backend/app/services/w4_question_core_inbound.py` | receipt·decision·binding 원자 적용 |
| W4 producer/outbox/relay | `epick_w4/question_core_producer.py`, `question_core_outbox.py`, `question_core_relay.py` | 실제 W4 image 경로 |

실제 secret, bearer, DB URL, temporary AWS credential, stable SenderId 값, account 전체 ARN은 문서에
포함하지 않았다. 실행 중에는 W4 send-only role의 stable SenderId와 W1 consumer 설정이
일치함을 preflight로 확인했다.

## 3. 실제 환경·권한 검증

| 경계 | 실제 상태 | 결과 |
| --- | --- | --- |
| PostgreSQL | 전용 `epick_w1_w4_ct12_runtime` 격리 DB | 운영/RDS 데이터 미사용 |
| W1 worker principal | worker 전용 login/RLS·runtime grants | preflight `worker_read_accessible` |
| W4 context principal | W1 DB의 column-limited read-only context login | owner/job/question/source 현재성 조회만 허용 |
| SQS | CT-12 전용 Main Queue + DLQ | redrive 결속·attribute 조회 통과 |
| W4 AWS principal | 전용 send-only assumed role | Main Queue `SendMessage` 경계로 실제 송신 |
| W1 AWS principal | 전용 Main Queue receive/delete/visibility 경계 | W1 consumer 수신·terminal delete 통과 |
| 네트워크 | private Worker EC2 / `worker_default` | W1 context adapter를 host port 없이 사용 |

W1 preflight 결과:

```json
{
  "status": "ok",
  "database": "worker_read_accessible",
  "queue": "attributes_accessible",
  "dlq": "attributes_accessible_and_bound",
  "principal": "configured"
}
```

## 4. 시나리오별 결과

| 시나리오 | 실행 경계 | 결과 | 부작용 |
| --- | --- | --- | --- |
| actual happy path | W4 actual producer → SQS → W1 actual consumer | `received=1`, `acknowledged=1`, `applied=1` | 최초 적용 1건 |
| explicit retry | W1 명시적 `RETRY` action | W2 command 1건, W1 outbox 1건 | receipt 단독으로는 command 0건 |
| duplicate | 동일 immutable W4 body를 SQS에 2회 전달 | 첫 번째 `applied=1`, 두 번째 `duplicate=1` | DB logical effect는 각 1건 |
| response loss after commit | W1 적용 후 W4 outbox transport state만 재시도 | `CORE_CONTEXT_NOT_CURRENT` | 늦은 재전송·command 0건 |
| relay restart | sent outbox로 relay 재시작 | `IDLE` | 추가 SQS 송신 0건 |
| cancel before send | W4 `PREPARED` 후 W1 Job 취소 | `BLOCKED / CORE_CONTEXT_NOT_CURRENT` | W1 영속 행 모두 0건 |
| owner deletion epoch before send | W4 `PREPARED` 후 owner epoch 증가 | `BLOCKED / CORE_CONTEXT_NOT_CURRENT` | W1 영속 행 모두 0건 |
| source-link change before send | W4 `PREPARED` 후 Job–Source input 결속 변경 | `BLOCKED / CORE_CONTEXT_NOT_CURRENT` | W1 영속 행 모두 0건 |
| malformed/principal/DB failure/ACK loss | W1 격리 synthetic runtime suite | terminal/retryable 분리, DB 재전달 후 1회 적용, ACK 유실 후 duplicate | W4 actual producer가 의도적 malformed/wrong-principal을 만들지는 않음 |

W1 격리 runtime 보조 결과는 다음과 같았다.

```json
{
  "status": "ok",
  "apply": "durable_then_acknowledged",
  "duplicate": "applied_once_then_acknowledged",
  "explicit_retry": "one_w1_command_and_outbox",
  "redelivery": "database_failure_then_applied",
  "ack_loss": "commit_then_duplicate_acknowledged"
}
```

## 5. 취소·삭제·관계 변경 판정

### 5.1 확정 순서

W4의 prepare는 W1 적용 권한이 아니다. W4 relay는 실제 송신 직전에 W1 context를
다시 resolve한다. 이 시점에 취소·owner deletion epoch·관계 변경이 먼저 확정되었으면
W4는 SQS에 전송하지 않는다.

W4가 이미 전송한 이후 취소·삭제가 경쟁하더라도 W1 consumer는 동일 owner/job/question/source
결속을 W1의 locked transaction 안에서 다시 검사한다. 따라서 사전 context 조회는 commit
권한이 아니며, W1 transaction 결과만 권위 있는 적용 결과다.

### 5.2 재노출·공용 Source

- 취소·삭제 epoch·source-link 변경 시나리오에서 새 receipt, decision, binding,
  command, W1 outbox는 모두 `0`이었다.
- W4 outbox는 immutable body를 변경하지 않고 `blocked / CORE_CONTEXT_NOT_CURRENT`를
  남겼다.
- owner deletion epoch 주입은 해당 합성 owner의 실행 결속만 무효화했다. Source
  행을 삭제하지 않았다. 공용 Source 비삭제 보장은 W1 DB race/shared-source
  integration suite와 함께 근거로 삼는다.

## 6. 증거 위치와 SHA-256

실행 호스트의 증거 디렉터리:

```text
/opt/epick/ct12/evidence
```

| 증거 파일 | SHA-256 |
| --- | --- |
| `actual-happy-path.json` | `66aed3c9e53418b63b05ac5e9c11b09495ead31a168c2265a452d0d29270fe4f` |
| `cancel-before-send.json` | `114089d7e04572b3cd7ce0ead14f9c892f3a75ea989c6ad14553a6eb9d4a129f` |
| `owner-epoch-before-send.json` | `3c085490fff73017f8ea3b65a1efd2029d15249e25caccc503655ce9967b2fdc` |
| `response-loss-after-commit.json` | `210ff4b8b8bb9438f96e4f39ac81a41633cf9d7443d73812e83e3d565a804ef1` |
| `response-loss-duplicate.json` | `d872e789b55c7f5a8e27b660ea2cd268db67a56b069ac284cd619820e7029f3f` |
| `source-link-change-before-send.json` | `d55097a95b63c219d8d2b49c44e2ee845a5d2c1ca1f9da7e9450adf8f179923f` |

전체 archive:

```text
/opt/epick/ct12/w1-w4-ct12-evidence-20260920.tar.gz
sha256:23d3fd3b85d3d2463050bcbf575900f7cb72d2f9463ccf72b15aac9f88f25bcc
```

모든 JSON과 sidecar checksum에 `sha256sum -c`를 적용해 모두 `OK`를 확인했고,
증거·checksum·archive는 실행 종료 시점에 read-only mode로 보존했다.

## 7. 재현성 보강 요청 — W4 조치 필요

W4 SHA `df41433218918e4167784243dc9b88e5a858278d`의
`deploy/question-core/compose.yaml`은 다음 표현을 사용했다.

```yaml
tmpfs: [/tmp:rw,noexec,nosuid,nodev,size=16m]
```

실제 Docker Compose에서 이 표현은 `nosuid` 등을 절대 경로로 해석해
`invalid mount path: 'nosuid' mount path must be absolute`로 실패했다. CT-12 호스트 복사는
아래처럼 하나의 문자열로 보정해 실행했다.

```yaml
tmpfs: ["/tmp:rw,noexec,nosuid,nodev,size=16m"]
```

W4는 위 보정을 접근 가능한 후속 commit에 반영하고 Linux Docker Compose 기동 결과를
회신해야 한다. 이 결함은 W4 runtime image 내부 코드의 성공 결과를 무효화하지는
않지만, 원본 compose의 재현 가능성이 아직 보완되지 않았음을 뜻한다.

## 8. W4 확인 요청

W4의 다음 회신은 새 API/event나 추가 신규 계약을 요구하는 것이 아니다.

1. 위 W1/W4 source SHA와 image digest를 W4 실제 CT-12 기준으로 확인
2. 정상·duplicate·response-loss/restart·cancel·owner epoch·source-link 변경 결과 수용
3. W4 후속 commit에 Compose `tmpfs` 보정 반영 및 full SHA 제공
4. REAL 사용자 자료 발행은 P2/P3 policy owner·revision 승인 전까지 계속 `DISABLED`임을 확인
5. W2 후속 확인이 필요하면 W1이 생성한 command/outbox 경계를 새 W4 계약이
   아닌 기존 W1–W2 protected lookup/commit-gate 계약으로 검증함을 확인

## 9. 종료 판정 기준

| 항목 | 현재 판정 | 해제 조건 |
| --- | --- | --- |
| W4 actual producer → W1 actual consumer | **PASS** | 추가 없음 |
| W4 durable outbox·response-loss·restart | **PASS** | 추가 없음 |
| duplicate·stale·cancel·delete epoch·relation change | **PASS** | 추가 없음 |
| W1 atomicity·terminal/retryable·DB/ACK failure | **PASS** | W1 격리 runtime/CI 근거 유지 |
| explicit retry → W1 command/outbox | **PASS** | 추가 없음 |
| W2 protected lookup/actual receipt | **PENDING** | W2가 기존 W1–W2 계약으로 해당 command를 확인 |
| W4 source Compose 재현성 | **W4 PATCH REQUIRED** | `tmpfs` 보정 commit/full SHA |
| REAL user-data enablement | **DISABLED** | P2/P3 승인 전 해제 금지 |
| CT-12 teardown | **PENDING** | 증거 외 임시 credential·container·DB·AWS 자원 정리 기록 |

`W1_W4_COMPLETE`는 W4가 Compose 보정을 회신하고, 필요한 W2 후속 확인과 CT-12
teardown이 기록된 뒤에만 선언한다. 현재 성공한 것은 명확히 **실제
W4→W1 runtime CT-12 경계**이며, 이를 REAL policy 승인이나 W2 최종 소비 완료로
확대 해석하지 않는다.
