# 내부 API 레퍼런스

이 문서는 사내 개발자용 내부 API 문서입니다.
외부 공개 API 문서는 docs.nexusai.co.kr 참조.

## 인증 방식

### API Key (기업 고객)
```
Authorization: Bearer nxs_live_xxxxxxxxxxxxxxxxxxxx
```
- 키 형식: `nxs_live_` + 32자 랜덤 문자열 (운영)
- 키 형식: `nxs_test_` + 32자 랜덤 문자열 (테스트)

### JWT (내부 서비스 간)
```
Authorization: Bearer <JWT Token>
X-Service-Name: ml-inference
```
- JWT Secret: Vault `secret/nexusbot/jwt-secret` 에서 조회
- 만료 시간: 1시간 (서비스 계정), 24시간 (사용자)

## 핵심 엔드포인트

### POST /api/v1/chat
대화 메시지 처리 (의도 분류 + 응답 생성)

**Request:**
```json
{
  "session_id": "sess_abc123",
  "message": "환불 신청하고 싶어요",
  "channel": "web",
  "org_id": "org_nexus_001"
}
```

**Response:**
```json
{
  "reply": "환불 신청을 도와드리겠습니다. 주문번호를 알려주세요.",
  "intent": "refund_request",
  "confidence": 0.94,
  "session_id": "sess_abc123",
  "handoff_required": false,
  "response_time_ms": 312
}
```

### POST /api/v1/sessions
새 대화 세션 생성

**Request:**
```json
{
  "org_id": "org_nexus_001",
  "user_id": "user_xyz",
  "channel": "kakao",
  "metadata": {"platform_version": "3.2.1"}
}
```

**Response:**
```json
{
  "session_id": "sess_abc123",
  "created_at": "2025-03-15T10:00:00Z",
  "expires_at": "2025-03-15T11:00:00Z"
}
```

### GET /api/v1/intents/{org_id}
조직의 의도 목록 조회

**Response:**
```json
{
  "intents": [
    {"id": "refund_request", "name": "환불 신청", "confidence_threshold": 0.85},
    {"id": "order_status", "name": "주문 상태 조회", "confidence_threshold": 0.80}
  ],
  "total": 42
}
```

## 에러 코드

| 코드 | HTTP 상태 | 설명 |
|------|-----------|------|
| E001 | 401 | 인증 실패 (API Key 유효하지 않음) |
| E002 | 403 | 권한 없음 |
| E003 | 404 | 세션 없음 또는 만료 |
| E004 | 429 | Rate Limit 초과 (플랜별 제한) |
| E005 | 503 | ML 추론 서버 일시적 오류 |

## Rate Limit 기준

| 플랜 | 분당 요청 | 일일 요청 |
|------|-----------|-----------|
| Starter | 20 req/min | 5,000 |
| Growth | 100 req/min | 30,000 |
| Enterprise | 1,000 req/min | 무제한 |
