"""
chat_server.py — 상주 챗봇 서버

Tauri 앱 시작 시 한 번 실행되어 계속 대기한다.
모델을 미리 로드하고 stdin 루프로 질문을 처리한다.

프로토콜:
  stdin  → JSON 한 줄
             질문: {"question": "...", "collection": "...", "top_k": 5, "alpha": 0.4}
             초기화: {"cmd": "reset"}
  stdout → JSON Lines 스트리밍
             {"status": "loading"}         시작 시 모델 로딩 알림
             {"status": "ready"}           준비 완료 (Rust가 이 시점까지 대기)
             {"status": "검색 중..."}      진행 상태
             {"t": "토큰"}                 LLM 스트리밍 토큰
             {"sources": [...]}            참고 문서 목록
             {"done": true}               응답 완료 신호
             {"error": "..."}             오류 발생 시
"""

import sys
import json
import os

sys.stdout.reconfigure(line_buffering=True)

_base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _base)

from dotenv import load_dotenv
load_dotenv(os.path.join(_base, ".env"))

os.environ.setdefault("HF_HUB_OFFLINE",      "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
DEFAULT_COL   = f"{os.getenv('VECTOR_DB_COLLECTION', 'confluence')}_{CHUNK_SIZE}_{CHUNK_OVERLAP}"

# ── 모델 사전 로드 ─────────────────────────────────────────────────────────────
print(json.dumps({"status": "loading"}), flush=True)

from retriever import _get_embedding_model, _get_rerank_model
_get_embedding_model()
_get_rerank_model()

from graph import build_graph
graph = build_graph()

print(json.dumps({"status": "ready"}), flush=True)

# ── 대화 히스토리 ──────────────────────────────────────────────────────────────
history: list[dict] = []  # [{"role": "user"/"assistant", "content": "..."}]


def _sources(context: list[dict]) -> list[dict]:
    """청크 목록에서 페이지별 출처 정보를 중복 없이 추출."""
    seen, sources = set(), []
    for h in context:
        pid = h["metadata"].get("page_id", "")
        if pid not in seen:
            seen.add(pid)
            sources.append({
                "title":      h["metadata"].get("title", ""),
                "url":        h["metadata"].get("url", ""),
                "breadcrumb": h["metadata"].get("breadcrumb", ""),
            })
    return sources


# ── 메인 루프 ──────────────────────────────────────────────────────────────────
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue

    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        continue

    # 히스토리 초기화
    if req.get("cmd") == "reset":
        history = []
        print(json.dumps({"done": True}), flush=True)
        continue

    question   = req.get("question", "")
    collection = req.get("collection", DEFAULT_COL)
    top_k      = int(req.get("top_k", 5))
    alpha      = float(req.get("alpha", 0.4))

    if not question:
        continue

    try:
        initial_state = {
            "question":   question,
            "collection": collection,
            "top_k":      top_k,
            "alpha":      alpha,
            "history":    history,
        }

        context      = []
        answer_parts = []

        for mode, data in graph.stream(initial_state, stream_mode=["messages", "updates"]):
            if mode == "updates":
                if "refine" in data:
                    refined_q = data["refine"].get("refined_query", "")
                    print(json.dumps({"status": f"검색 중... ({refined_q})"}), flush=True)
                elif "retrieve" in data:
                    context  = data["retrieve"].get("context", [])
                    page_cnt = len({c["metadata"].get("page_id") for c in context})
                    print(json.dumps({"status": f"{page_cnt}개 문서 분석 중..."}), flush=True)
                elif "generate" in data:
                    print(json.dumps({"status": ""}), flush=True)
            elif mode == "messages":
                msg, metadata = data
                if metadata.get("langgraph_node") != "generate":
                    continue
                if hasattr(msg, "content") and msg.content:
                    content = msg.content
                    if isinstance(content, str):
                        answer_parts.append(content)
                        print(json.dumps({"t": content}), flush=True)
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                answer_parts.append(block["text"])
                                print(json.dumps({"t": block["text"]}), flush=True)

        # 히스토리 누적
        history.append({"role": "user",      "content": question})
        history.append({"role": "assistant", "content": "".join(answer_parts)})

        print(json.dumps({"sources": _sources(context)}), flush=True)
        print(json.dumps({"done": True}), flush=True)

    except Exception as e:
        print(json.dumps({"error": str(e)}), flush=True)
        print(json.dumps({"done": True}), flush=True)
