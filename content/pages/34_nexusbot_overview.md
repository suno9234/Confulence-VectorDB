# NexusBot Platform 개요

## 제품 설명

NexusBot은 기업 고객 서비스를 자동화하는 AI 챗봇 SaaS 플랫폼입니다.
자연어 처리(NLP) 기반의 의도 분류 + 자체 파인튜닝된 LLM을 결합하여
고객 문의의 70~85%를 상담원 개입 없이 처리합니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| 의도 분류 | 고객 메시지를 최대 500개 의도 카테고리로 분류 |
| 자연어 응답 생성 | 사내 파인튜닝 LLM 기반 응답 (Nexus-LLM-7B) |
| 대화 흐름 설계 | 드래그앤드롭 방식의 시나리오 빌더 |
| 상담원 연결 | 챗봇 해결 불가 시 Human Handoff 기능 |
| 다채널 지원 | 웹 위젯, 카카오 채널, 슬랙, REST API |
| 분석 대시보드 | 실시간 대화 분석, 해결률, CSAT 리포트 |
| 다국어 지원 | 한국어, 영어, 일본어 (자동 언어 감지) |

## 플랜 구조 (2025년 기준)

| 플랜 | 월 대화 수 | 월 요금 | 주요 제한 |
|------|-----------|---------|-----------|
| Starter | 5,000건 | 290,000원 | 1개 채널, 100개 의도 |
| Growth | 30,000건 | 890,000원 | 3개 채널, 300개 의도 |
| Enterprise | 무제한 | 협의 | 전체 기능, SLA 보장 |
| On-premise | 별도 | 협의 | 자사 서버 설치 |

## 내부 서비스명과 외부 제품명 매핑

| 내부 서비스명 | 외부 제품명 | 레포 |
|--------------|------------|------|
| nexusbot-api | NexusBot Core API | nexusbot-api |
| nexusbot-frontend | NexusBot Admin Console | nexusbot-frontend |
| nexusbot-ml | NexusBot AI Engine | nexusbot-ml |
| nexus-llm-7b | Nexus LLM | nexusbot-ml/models |

## 서비스 의존성

```
고객 브라우저
    │
    ▼
CloudFront CDN
    │
    ▼
ALB (Application Load Balancer)
    ├── nexusbot-api (FastAPI, EKS)
    │     ├── PostgreSQL (RDS)
    │     ├── Redis (ElastiCache)
    │     └── ml-inference (EKS, GPU 노드)
    └── nexusbot-frontend (Next.js, EKS)
```
