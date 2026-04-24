# 모델 학습 파이프라인

## 보유 모델 현황 (2025년 3월 기준)

| 모델명 | 역할 | 기반 모델 | 현재 버전 | 학습 주기 |
|--------|------|-----------|-----------|-----------|
| Nexus-Intent-v3 | 의도 분류 | KoELECTRA-base-v3 | v3.8.2 | 월 1회 |
| Nexus-LLM-7B | 응답 생성 | LLaMA3-7B | v2.1.0 | 분기 1회 |
| Nexus-Embed-v1 | 텍스트 임베딩 | klue/roberta-base | v1.4.0 | 분기 1회 |

## 학습 환경

- **서버**: ml-train-01 (10.10.6.10)
- **GPU**: NVIDIA A100 40GB × 4장
- **OS**: Ubuntu 22.04 + CUDA 12.1
- **프레임워크**: PyTorch 2.1, Hugging Face Transformers 4.38
- **실험 관리**: MLflow (mlflow.nexusai.internal)
- **모델 저장**: MLflow Model Registry + S3 (s3://nexusai-models/)

## Nexus-Intent-v3 학습 파이프라인

### 데이터 준비
```bash
# S3에서 최신 학습 데이터 다운로드
python scripts/prepare_intent_data.py \
  --s3-path s3://nexusai-datalake/model-ready/intent-clf/ \
  --days 90 \
  --output data/intent_train.jsonl
```

### 학습 실행
```bash
python train_intent_classifier.py \
  --model klue/roberta-base \
  --data data/intent_train.jsonl \
  --epochs 5 \
  --batch-size 64 \
  --lr 2e-5 \
  --output models/intent-v3/ \
  --mlflow-experiment "intent-classifier"
```

소요 시간: 약 3시간 (데이터 820만 쌍, A100 × 4)

### 평가 기준 (모델 교체 조건)
- 기존 모델 대비 전체 F1 +0.5% 이상
- 상위 20개 의도 카테고리 개별 F1 ≥ 0.90
- 추론 지연시간 P99 ≤ 80ms (현재 모델 기준 유지)

## Nexus-LLM-7B 파인튜닝 파이프라인

### 방법: LoRA (Low-Rank Adaptation)
```python
# configs/llm_lora_config.yaml
lora_r: 16
lora_alpha: 32
lora_dropout: 0.05
target_modules: ["q_proj", "v_proj"]
```

### 학습 실행
```bash
python finetune_llm.py \
  --base-model meta-llama/Meta-Llama-3-8B \
  --lora-config configs/llm_lora_config.yaml \
  --data s3://nexusai-datalake/model-ready/llm-finetune/ \
  --epochs 3 \
  --batch-size 8 \
  --gradient-accumulation 4 \
  --output s3://nexusai-models/nexus-llm-7b/
```

소요 시간: 약 18시간 (A100 × 4, DeepSpeed ZeRO-2)

## 모델 배포 프로세스

1. MLflow에서 모델 성능 비교 확인
2. AI/ML팀장(이서연) 검토 및 승인
3. 스테이징 환경 배포 후 A/B 테스트 (1주일)
4. A/B 결과: CSAT +0.2% 이상 또는 해결률 +1% 이상 시 운영 배포
5. 운영 배포: CTO 최종 승인 → 인프라팀 모델 스왑

## 모델 모니터링

- **대시보드**: Grafana "AI Model Performance" (grafana.nexusai.internal:3000)
- **주요 지표**: 의도 분류 신뢰도 분포, LLM 응답 길이, 추론 레이턴시
- **드리프트 감지**: 주간 자동 실행 (weekly_model_eval DAG)
  - 의도별 정확도가 기준치 대비 5% 이상 하락 시 Slack 알림
