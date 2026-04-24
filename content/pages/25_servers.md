# 서버 목록 & 접속 정보

**접근 권한 필요**: 아래 서버 접속은 IT지원팀 승인 후 가능합니다.

## 운영 서버 (Production)

| 서버명 | IP | 역할 | OS | 담당팀 |
|--------|----|------|----|--------|
| api-prod-01 | 10.10.2.10 | API 서버 (Primary) | Ubuntu 22.04 | 플랫폼개발팀 |
| api-prod-02 | 10.10.2.11 | API 서버 (Secondary) | Ubuntu 22.04 | 플랫폼개발팀 |
| worker-prod-01 | 10.10.2.20 | 백그라운드 잡 처리 | Ubuntu 22.04 | 플랫폼개발팀 |
| ml-inference-01 | 10.10.2.30 | ML 모델 추론 서버 | Ubuntu 22.04 | AI/ML팀 |
| ml-inference-02 | 10.10.2.31 | ML 모델 추론 서버 | Ubuntu 22.04 | AI/ML팀 |
| db-prod-01 | 10.10.3.10 | PostgreSQL 15 (Primary) | Ubuntu 22.04 | 인프라팀 |
| db-prod-02 | 10.10.3.11 | PostgreSQL 15 (Replica) | Ubuntu 22.04 | 인프라팀 |
| redis-prod-01 | 10.10.3.20 | Redis 7 (캐시/세션) | Ubuntu 22.04 | 인프라팀 |
| es-prod-01 | 10.10.3.30 | Elasticsearch 8 | Ubuntu 22.04 | 인프라팀 |

## 개발/스테이징 서버

| 서버명 | IP | 역할 | OS |
|--------|----|------|----|
| dev-api-01 | 10.10.4.10 | 개발용 API 서버 | Ubuntu 22.04 |
| staging-api-01 | 10.10.5.10 | 스테이징 API 서버 | Ubuntu 22.04 |
| dev-db-01 | 10.10.4.20 | 개발용 PostgreSQL | Ubuntu 22.04 |
| ml-train-01 | 10.10.6.10 | 모델 학습 (GPU: A100 x4) | Ubuntu 22.04 |

## 내부 서비스 서버 (사무실)

| 서버명 | IP | 역할 |
|--------|----|------|
| git.nexusai.internal | 192.168.1.11 | GitLab CE |
| jira.nexusai.internal | 192.168.1.12 | Atlassian Jira |
| confluence.nexusai.internal | 192.168.1.12 | Atlassian Confluence |
| jenkins.nexusai.internal | 192.168.1.13 | Jenkins CI/CD |
| grafana.nexusai.internal | 192.168.1.14 | Grafana + Prometheus |
| vault.nexusai.internal | 192.168.1.15 | HashiCorp Vault |
| harbor.nexusai.internal | 192.168.1.16 | Harbor 컨테이너 레지스트리 |

## 접속 방법

- **SSH**: `ssh -i ~/.ssh/nexusai_rsa <username>@<IP>` (VPN 연결 필수)
- **SSH 키 발급**: IT지원팀 박준혁에게 요청 (공개 키 제출)
- **DB 접속**: DBeaver 사용 권장, DB 계정은 팀장 요청 후 발급
- **서버 비밀번호**: HashiCorp Vault (vault.nexusai.internal) 에서 조회
