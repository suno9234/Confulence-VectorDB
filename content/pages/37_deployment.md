# 배포 프로세스

## 배포 환경

| 환경 | 도메인 | K8s 네임스페이스 | 용도 |
|------|--------|-----------------|------|
| 개발 | dev-api.nexusai.internal | development | 개발자 테스트 |
| 스테이징 | staging-api.nexusai.internal | staging | QA 및 릴리즈 검증 |
| 운영 | api.nexusai.co.kr | production | 실제 서비스 |

## 배포 절차 (정규 배포)

### 1단계: 스테이징 배포 (자동)
main 브랜치 머지 시 Jenkins가 자동 실행:
```
1. Docker 이미지 빌드 (harbor.nexusai.internal/nexusbot/api:sha-xxxxxx)
2. K8s 스테이징 네임스페이스 Rolling Update
3. 스테이징 smoke test 자동 실행
4. 슬랙 #deploy-log 에 결과 알림
```

### 2단계: QA 검증
- QA팀(윤지혜 팀장)이 스테이징 환경에서 기능 검증
- 체크리스트: QA팀 공유 드라이브 `QA > 검증 체크리스트 > vX.Y.md`
- 검증 완료 시 #deploy-log 에 `✅ QA 승인: vX.Y.Z` 메시지

### 3단계: 운영 배포 (수동 트리거)
```bash
# Jenkins에서 수동 실행 (팀장 이상)
# 또는 Jenkins UI: Pipelines > nexusbot-api-prod > Build with Parameters
# TAG: harbor.nexusai.internal/nexusbot/api:sha-xxxxxx
```

K8s Rolling Update 순서:
```
api-prod-01 (배포) → 헬스체크 통과 → api-prod-02 (배포)
```

## 배포 시간 제한

- **배포 금지 시간**: 금요일 15:00 이후 (긴급 핫픽스 제외)
- **권장 배포 시간**: 화~목 10:00–14:00 (트래픽 저점)
- **연휴 전날**: 배포 금지 (COO 사전 승인 시 예외)

## 핫픽스 배포 절차

1. `hotfix/JIRA-ID-desc` 브랜치 생성
2. CTO 또는 팀장이 코드 리뷰 (최대 1시간 내)
3. main 머지 → 스테이징 자동 배포
4. QA팀 최소 검증 (30분 이내)
5. 운영 배포 (CTO 또는 해당 팀장 승인)

## 배포 후 모니터링

배포 직후 15분간 Grafana 대시보드 모니터링 필수:
- **URL**: grafana.nexusai.internal:3000
- **대시보드**: "NexusBot Production Overview"
- **모니터링 지표**: 에러율, P99 응답시간, Pod 재시작 수

## 롤백 기준

아래 상황 발생 시 즉시 롤백 결정:
- 에러율 0.5% 초과 (배포 전 대비 3배 이상)
- P99 응답시간 2,000ms 초과
- Pod CrashLoopBackOff 발생
- 슬랙 #alert-prod 에 P1 알림 2회 이상
