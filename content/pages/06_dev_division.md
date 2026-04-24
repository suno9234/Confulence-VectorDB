# 개발본부

**본부장**: 김민수 CTO (ms.kim@nexusai.co.kr / 내선 7710)
**총 인원**: 30명

## 팀 구성

### 플랫폼개발팀 (10명)
- **팀장**: 정우성 (ws.jung@nexusai.co.kr / 내선 7711)
- **역할**: NexusBot 웹 대시보드, 관리자 콘솔, 고객 포털 개발
- **주요 기술**: React, TypeScript, Node.js, PostgreSQL
- **스프린트**: 2주 단위, 매주 월요일 Sprint Planning
- **Jira 프로젝트 키**: PLAT

### AI/ML팀 (8명)
- **팀장**: 이서연 (sy.lee@nexusai.co.kr / 내선 7712)
- **역할**: 챗봇 언어 모델 개발 및 파인튜닝, 의도 분류, 대화 품질 개선
- **주요 기술**: Python, PyTorch, Hugging Face Transformers, MLflow
- **스프린트**: 3주 단위 (모델 실험 사이클 기준)
- **Jira 프로젝트 키**: AIML

### 인프라팀 (6명)
- **팀장**: 강태민 (tm.kang@nexusai.co.kr / 내선 7713)
- **역할**: 클라우드 인프라 운영(AWS), CI/CD, 보안, 모니터링
- **주요 기술**: Terraform, Kubernetes(EKS), GitHub Actions, Datadog
- **온콜 스케줄**: 주 1회 순환, #alert-prod 채널 연동
- **Jira 프로젝트 키**: INFRA

### QA팀 (6명)
- **팀장**: 윤지혜 (jh.yoon@nexusai.co.kr / 내선 7714)
- **역할**: 기능 테스트, 자동화 테스트, 배포 전 검증, 버그 트래킹
- **주요 기술**: Playwright, Jest, k6 (부하테스트)
- **Jira 프로젝트 키**: QA

## 개발본부 공통 규칙

- 코드 리뷰: PR당 최소 1명 Approve 필수 (시니어 이상)
- 코드 리뷰 SLA: 영업일 기준 1일 이내 1차 리뷰
- 장애 대응: P1 장애는 15분 이내 초기 대응, COO에게 문자 보고
- 개발 문서: 모든 API 변경 사항은 이 위키에 반영 필수

## 정기 회의 일정

| 회의명 | 주기 | 시간 | 참석자 |
|--------|------|------|--------|
| 개발본부 주간 회의 | 매주 월요일 | 10:00–11:00 | 전 팀장 + CTO |
| 아키텍처 리뷰 | 격주 수요일 | 14:00–15:00 | 시니어 개발자 이상 |
| 장애 사후 리뷰 | 장애 발생 후 2일 이내 | — | 관련 팀 전원 |
