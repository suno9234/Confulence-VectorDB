# 개발 환경 개요

## 기술 스택 요약

### 프론트엔드
- **언어**: TypeScript 5.x
- **프레임워크**: React 18, Next.js 14
- **상태관리**: Zustand
- **스타일**: Tailwind CSS
- **빌드**: pnpm + Vite

### 백엔드 (API)
- **언어**: Python 3.11
- **프레임워크**: FastAPI
- **ORM**: SQLAlchemy 2.0
- **DB**: PostgreSQL 15, Redis 7
- **검색**: Elasticsearch 8
- **메시지 큐**: AWS SQS + Celery

### AI/ML
- **언어**: Python 3.11
- **프레임워크**: PyTorch 2.x, Hugging Face Transformers
- **실험 관리**: MLflow (mlflow.nexusai.internal)
- **모델 서빙**: FastAPI + Triton Inference Server

### 인프라
- **클라우드**: AWS (ap-northeast-2)
- **컨테이너**: Docker + Kubernetes (EKS 1.29)
- **IaC**: Terraform
- **CI/CD**: GitHub Actions (외부) + Jenkins (내부)
- **모니터링**: Grafana + Prometheus + Datadog

## 레포지토리 목록 (git.nexusai.internal)

| 레포 이름 | 설명 | 주 담당팀 |
|-----------|------|-----------|
| nexusbot-api | 핵심 API 서버 (FastAPI) | 플랫폼개발팀 |
| nexusbot-frontend | 관리자 대시보드 (Next.js) | 플랫폼개발팀 |
| nexusbot-ml | AI 모델 학습 코드 | AI/ML팀 |
| nexusbot-infra | Terraform, K8s manifests | 인프라팀 |
| nexusbot-sdk | 고객사 제공 SDK (Python, Node.js) | 플랫폼개발팀 |
| nexusbot-docs | 공개 API 문서 (docs.nexusai.co.kr) | 플랫폼개발팀 |

## 개발 원칙

1. **테스트 커버리지**: 신규 코드 80% 이상 유지 (PR 머지 조건)
2. **린팅**: Python은 ruff, TypeScript는 ESLint + Prettier (pre-commit hook)
3. **타입 힌팅**: Python 전 함수에 타입 힌트 필수
4. **시크릿 관리**: 코드에 시크릿 절대 금지, Vault 또는 AWS Secrets Manager 사용
