# 시스템 아키텍처

## 전체 아키텍처 다이어그램

```
[고객 채널]
웹 위젯 / 카카오 채널 / 슬랙 / REST API
      │
      ▼
[CDN & 진입점]
CloudFront → ALB (SSL 종단)
      │
      ├── /app, /admin → nexusbot-frontend (Next.js, 3개 Pod)
      └── /api/v1/*    → nexusbot-api (FastAPI, 4개 Pod)
                              │
           ┌─────────────────┼──────────────────┐
           ▼                 ▼                   ▼
      PostgreSQL 15      Redis 7           ml-inference
      (RDS, Multi-AZ)   (ElastiCache)    (FastAPI+Triton)
                                               │
                                          Nexus-LLM-7B
                                          (GPU: A100 x2)
```

## 주요 컴포넌트 상세

### nexusbot-api (FastAPI)
- **역할**: 핵심 비즈니스 로직, 대화 세션 관리, 인증/인가
- **배포**: EKS, 4 Replica, HPA (CPU 70% 이상 시 자동 스케일 아웃, 최대 10개)
- **리소스**: 요청당 2 vCPU / 4GB RAM
- **주요 엔드포인트**: `/api/v1/chat`, `/api/v1/sessions`, `/api/v1/intents`

### ml-inference (추론 서버)
- **역할**: 의도 분류 + LLM 응답 생성
- **모델**: Nexus-LLM-7B (자체 파인튜닝, LLaMA3 기반)
- **배포**: EKS GPU 노드풀, 2 Replica 고정
- **GPU**: NVIDIA A100 40GB (인스턴스: p3.2xlarge)
- **평균 추론 시간**: 의도 분류 45ms / 응답 생성 280ms

### PostgreSQL (RDS)
- **버전**: 15.4
- **인스턴스**: db.r6g.xlarge (운영), db.t3.medium (스테이징)
- **Multi-AZ**: 운영 환경 활성화
- **백업**: 매일 02:00 자동 스냅샷 (30일 보관)
- **주요 스키마**: organizations, sessions, messages, intents, users

### Redis (ElastiCache)
- **버전**: 7.0
- **인스턴스**: cache.r6g.large (2개 Replica)
- **용도**: 세션 캐시 (TTL 24h), API Rate Limiting, 실시간 카운터

## 성능 목표 (SLA)

| 지표 | 목표 | 현재 (2025년 3월) |
|------|------|------------------|
| API 응답시간 P50 | < 200ms | 145ms |
| API 응답시간 P99 | < 800ms | 820ms |
| 가용성 | 99.9% | 99.87% |
| LLM 추론 P50 | < 300ms | 280ms |
| 에러율 | < 0.1% | 0.06% |

## 재해 복구 (DR)

- **RPO (복구 목표 시점)**: 1시간 (RDS 스냅샷 기준)
- **RTO (복구 목표 시간)**: 2시간
- **DR 훈련**: 연 1회 (1월, 인프라팀 주관)
