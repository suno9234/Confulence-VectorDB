# 데이터 수집 & 전처리

## 수집 대상 데이터

| 데이터 종류 | 소스 | 수집 주기 | 저장 위치 |
|-------------|------|-----------|-----------|
| 대화 로그 | nexusbot PostgreSQL | 매일 02:00 | S3 /raw/conversations/ |
| 의도 분류 결과 | nexusbot PostgreSQL | 매일 02:00 | S3 /raw/intents/ |
| 상담원 수동 라벨 | 관리자 콘솔 DB | 실시간 Trigger | S3 /raw/labels/ |
| CSAT 피드백 | 고객 설문 DB | 매일 03:00 | S3 /raw/csat/ |

## 전처리 파이프라인 (Airflow DAG: daily_conversation_pipeline)

### Task 1: extract_raw_data
```python
# nexusbot PostgreSQL에서 전날 데이터 추출
# 쿼리 위치: nexusbot-ml/dags/sql/extract_conversations.sql
SELECT session_id, message, response, intent, confidence, created_at
FROM messages
WHERE created_at >= %s AND created_at < %s
  AND status = 'completed'
```
소요 시간: 약 8분 (14만 건 기준)

### Task 2: mask_pii
개인정보 마스킹 처리:
- 전화번호 패턴 → `[PHONE]`
- 주민등록번호 → `[RRN]`
- 이메일 → `[EMAIL]`
- 이름 (사전 기반) → `[NAME]`
- 신용카드 번호 → `[CARD]`

마스킹 라이브러리: 사내 개발 `nexus-pii-masker` (v1.3.0, PyPI 내부 등록)

### Task 3: quality_filter
다음 기준으로 저품질 데이터 필터링:
- 메시지 길이 5자 미만 제거
- 의도 신뢰도 0.7 미만 제거 (학습용에서만)
- 반복 메시지 제거 (동일 세션 내 90% 이상 유사)
- 욕설/부적절 표현 필터 (블랙리스트 1,240개 단어)

필터링 후 잔류율: 약 73% (일 약 10.2만 건)

### Task 4: generate_training_pairs
필터링된 데이터에서 학습 쌍 생성:
- (질문, 정답 의도) 쌍 → 의도 분류 모델 학습용
- (질문, 상담원 수정 응답) 쌍 → LLM 파인튜닝용 (상담원 라벨 있는 경우만)

### Task 5: upload_to_s3
```
S3 경로 규칙:
s3://nexusai-datalake/processed/conversations/YYYY/MM/DD/
s3://nexusai-datalake/model-ready/intent-clf/YYYY/MM/DD/
s3://nexusai-datalake/model-ready/llm-finetune/YYYY/MM/DD/
```

## 데이터 품질 지표 (SLA)

| 지표 | 목표 | 모니터링 |
|------|------|----------|
| 파이프라인 성공률 | 99% 이상 | Airflow 알림 |
| PII 마스킹 누락률 | 0.01% 미만 | 주간 샘플링 검사 |
| 데이터 레이턴시 | 02:00 실행 → 06:00 완료 | Airflow SLA 설정 |

파이프라인 실패 시: 슬랙 #alert-prod 알림 + 이서연, 강태민에게 DM
