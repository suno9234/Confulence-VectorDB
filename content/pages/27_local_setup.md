# 로컬 개발 환경 설정

## 사전 조건

- macOS 13 이상 (Apple Silicon 권장)
- VPN 연결 상태 (git.nexusai.internal 접근 필요)
- IT지원팀에서 SSH 키 및 GitLab 계정 발급 완료

## 공통 도구 설치

```bash
# Homebrew 설치 (없는 경우)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 공통 도구
brew install git python@3.11 node nvm pnpm docker colima

# Python 버전 관리
brew install pyenv
pyenv install 3.11.9
pyenv global 3.11.9

# AWS CLI
brew install awscli
aws configure  # 계정 정보는 Vault에서 조회
```

## 백엔드 (nexusbot-api) 셋업

```bash
git clone git@git.nexusai.internal:dev/nexusbot-api.git
cd nexusbot-api

# 가상환경 생성
python -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -r requirements/dev.txt

# 환경변수 설정
cp .env.example .env.local
# .env.local 파일을 열어 필요한 값 입력 (Vault에서 조회)

# 로컬 DB/Redis 실행 (Docker)
docker compose -f docker-compose.dev.yml up -d

# DB 마이그레이션
alembic upgrade head

# 개발 서버 실행
uvicorn app.main:app --reload --port 8000
```

API 서버 확인: http://localhost:8000/docs

## 프론트엔드 (nexusbot-frontend) 셋업

```bash
git clone git@git.nexusai.internal:dev/nexusbot-frontend.git
cd nexusbot-frontend

pnpm install

cp .env.example .env.local
# NEXT_PUBLIC_API_URL=http://localhost:8000

pnpm dev
```

프론트엔드 확인: http://localhost:3000

## 자주 발생하는 문제

| 증상 | 원인 | 해결 방법 |
|------|------|-----------|
| git clone 실패 | VPN 미연결 | VPN 연결 후 재시도 |
| DB 연결 오류 | Docker 미실행 | `colima start` 후 `docker compose up` |
| 포트 충돌 | 8000번 포트 사용 중 | `lsof -i :8000` 으로 확인 후 종료 |
| M1/M2 패키지 오류 | arm64 미지원 패키지 | `arch -x86_64` 접두사 붙여 실행 |

## 문의

개발 환경 문제는 슬랙 #dev-all 채널 또는 각 팀 채널에 질문하세요.
