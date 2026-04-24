# 데이터 파이프라인 개요

## 데이터 흐름 전체 구조

```
[데이터 소스]
NexusBot 대화 로그 (PostgreSQL)
    │
    ▼
[수집 & 전처리]
Airflow DAG (매일 02:00 KST 실행)
- 전날 대화 로그 추출
- 개인정보 마스킹
- 정제 및 품질 필터링
    │
    ▼
[저장]
AWS S3 (nexusai-datalake)
  ├── /raw/         원본 데이터 (90일 보관)
  ├── /processed/   정제 데이터 (1년 보관)
  └── /model-ready/ 학습용 데이터 (영구 보관)
    │
    ▼
[활용]
├── MLflow 모델 학습 (AI/ML팀)
├── NexusAnalytics (고객 분석 대시보드)
└── 내부 BI (Redash, redash.nexusai.internal)
```

## 파이프라인 담당

| 역할 | 담당자 | 연락처 |
|------|--------|--------|
| 파이프라인 설계/운영 | 이서연 (AI/ML팀장) | sy.lee@nexusai.co.kr |
| Airflow 인프라 | 강태민 (인프라팀장) | tm.kang@nexusai.co.kr |
| 데이터 품질 관리 | AI/ML팀 권재원 | jw.kwon@nexusai.co.kr |

## 데이터 규모 (2025년 3월 기준)

| 지표 | 값 |
|------|-----|
| 일 신규 대화 로그 | 약 14만 건 |
| 일 신규 메시지 수 | 약 85만 개 |
| 누적 처리 대화 수 | 약 1.2억 건 |
| S3 총 데이터 용량 | 약 3.8TB |
| 학습용 데이터셋 크기 | 약 820만 쌍 (질문-답변) |

## Airflow 접속

- **URL**: airflow.nexusai.internal
- **로그인**: 구글 SSO
- **주요 DAG**:
  - `daily_conversation_pipeline`: 매일 02:00 실행
  - `weekly_model_eval`: 매주 월요일 03:00 실행
  - `monthly_data_quality_report`: 매월 1일 04:00 실행

## 데이터 접근 권한

- S3 버킷(`nexusai-datalake`)은 AI/ML팀 + 인프라팀만 접근
- 타 팀 데이터 분석 필요 시: Redash(redash.nexusai.internal)에서 조회
- 고객 원본 데이터 접근: CTO + COO 이중 승인 필요
