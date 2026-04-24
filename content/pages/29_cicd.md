# CI/CD 파이프라인

## 파이프라인 구성

넥서스AI의 CI/CD는 **Jenkins** (jenkins.nexusai.internal)를 중심으로 운영됩니다.

```
개발자 Push
    │
    ▼
GitLab Webhook
    │
    ▼
Jenkins CI Pipeline
  ├── 1. 코드 체크아웃
  ├── 2. 린팅 (ruff / ESLint)
  ├── 3. 단위 테스트 (pytest / Jest)
  ├── 4. 통합 테스트
  ├── 5. 커버리지 리포트 (80% 미만 시 실패)
  ├── 6. Docker 이미지 빌드
  └── 7. Harbor 레지스트리 Push
    │
    ▼ (main 머지 시)
Jenkins CD Pipeline
  ├── 1. 스테이징 배포 (staging-api-01)
  ├── 2. 스테이징 E2E 테스트 (Playwright)
  ├── 3. QA팀 승인 대기 (슬랙 #deploy-log 알림)
  └── 4. 운영 배포 (api-prod-01/02, Rolling Update)
```

## 환경별 배포 주기

| 환경 | 트리거 | 담당 승인자 |
|------|--------|-------------|
| 개발(dev) | feature 브랜치 push 시 자동 | 없음 (자동) |
| 스테이징 | main 머지 시 자동 | 없음 (자동) |
| 운영(prod) | 스테이징 검증 후 수동 트리거 | QA팀장 → 팀장 |

## Jenkins 접속

- URL: jenkins.nexusai.internal
- 로그인: 구글 SSO (회사 계정)
- 권한: 개발자는 파이프라인 조회/빌드 실행 가능, 설정 변경은 인프라팀만

## 운영 배포 절차 (상세)

1. QA팀장(윤지혜)이 스테이징 테스트 완료 후 #deploy-log 에 `@팀장 배포 승인 요청` 메시지
2. 해당 팀장이 Jenkins 운영 배포 파이프라인 수동 실행
3. Jenkins가 K8s Rolling Update 실행 (api-prod-01 → api-prod-02 순서)
4. Grafana 대시보드(grafana.nexusai.internal:3000)에서 에러율/응답시간 모니터링
5. 배포 완료 후 5분간 이상 없으면 #deploy-log 에 완료 메시지

## 롤백 방법

```bash
# Jenkins UI에서 이전 성공 빌드 선택 → "Deploy to Production" 버튼
# 또는 kubectl로 직접 (인프라팀 권한 필요)
kubectl rollout undo deployment/nexusbot-api -n production
```

## 알림 설정

- Jenkins 빌드 실패 → 슬랙 #deploy-log + 커밋 작성자에게 DM
- 운영 배포 시작/완료 → 슬랙 #deploy-log
- E2E 테스트 실패 → 슬랙 #alert-prod + QA팀 전원 DM
