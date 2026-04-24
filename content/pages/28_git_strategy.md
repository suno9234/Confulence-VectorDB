# Git 브랜치 전략

넥서스AI는 **GitHub Flow** 기반의 단순한 브랜치 전략을 사용합니다.

## 브랜치 구조

```
main (운영 배포)
  └── feature/PLAT-123-login-fix      (기능 개발)
  └── fix/PLAT-456-memory-leak        (버그 수정)
  └── hotfix/PLAT-789-critical-crash  (긴급 수정)
  └── release/v2.5.0                  (릴리즈 준비)
```

## 브랜치 네이밍 규칙

| 유형 | 형식 | 예시 |
|------|------|------|
| 기능 개발 | `feature/JIRA-ID-brief-desc` | `feature/PLAT-123-oauth-login` |
| 버그 수정 | `fix/JIRA-ID-brief-desc` | `fix/AIML-456-token-overflow` |
| 긴급 핫픽스 | `hotfix/JIRA-ID-brief-desc` | `hotfix/INFRA-789-db-conn` |
| 릴리즈 | `release/vX.Y.Z` | `release/v2.5.0` |
| 실험적 작업 | `experiment/brief-desc` | `experiment/gpt4o-eval` |

## 커밋 메시지 규칙 (Conventional Commits)

```
<type>(<scope>): <subject>

[optional body]
[optional footer]
```

| type | 사용 시점 |
|------|-----------|
| feat | 새로운 기능 추가 |
| fix | 버그 수정 |
| refactor | 기능 변경 없는 코드 개선 |
| test | 테스트 추가/수정 |
| docs | 문서 변경 |
| chore | 빌드, 설정 변경 |
| perf | 성능 개선 |

예시:
```
feat(auth): add Google OAuth2 login support

- Add Google OAuth2 provider to FastAPI auth router
- Store OAuth tokens in Redis with 24h TTL

Closes PLAT-123
```

## PR 규칙

- **PR 제목**: 커밋 메시지 규칙과 동일 형식
- **PR 템플릿**: `.github/PULL_REQUEST_TEMPLATE.md` 자동 적용
- **필수 항목**: 변경 요약, 테스트 방법, 스크린샷(UI 변경 시)
- **리뷰어**: 최소 1명 Approve (시니어 이상), 팀장 최종 머지
- **리뷰 SLA**: 영업일 1일 이내 1차 리뷰
- **Draft PR**: WIP 상태는 Draft로 올리고, 준비 완료 시 Ready for Review 전환

## main 브랜치 보호 규칙

- 직접 push 금지 (force push도 금지)
- PR 머지 전 CI 통과 필수 (Jenkins 자동 실행)
- 최소 1명 Approve 없으면 머지 불가
- 머지 방식: **Squash and Merge** (커밋 히스토리 단순화)
