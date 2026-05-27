"""
chat_server.py — 상주 챗봇 서버

Tauri 앱 시작 시 한 번 실행되어 계속 대기한다.
모델을 미리 로드하고 stdin 루프로 질문을 처리한다.
대화 히스토리는 chat_history.json으로 유지되어 앱 재시작 후에도 이어진다.

사용법:
    python chat_server.py <cwd>   (cwd: 프로젝트 루트. 히스토리 파일 위치)

프로토콜:
  stdin  → JSON 한 줄
             질문: {"question": "...", "collection": "...", "top_k": 5, "alpha": 0.4}
             초기화: {"cmd": "reset"}
  stdout → JSON Lines 스트리밍
             {"status": "loading"}
             {"status": "ready", "has_history": bool, "turns": int}
             {"status": "..."}   진행 상태
             {"t": "토큰"}       LLM 스트리밍 토큰
             {"sources": [...]}  참고 문서
             {"done": true}      응답 완료
             {"error": "..."}    오류
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

# ── 히스토리 파일 경로 (cwd는 Rust에서 전달) ──────────────────────────────────
_cwd          = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
HISTORY_FILE  = os.path.join(_cwd, "chat_history.json")

# ── 히스토리 관리 상수 ─────────────────────────────────────────────────────────
HISTORY_LIMIT = 12   # 이 수 초과 시 요약 트리거 (메시지 기준, = 6턴)
KEEP_RECENT   = 8    # 요약 후 유지할 메시지 수 (= 4턴)

# ── 모델 사전 로드 ─────────────────────────────────────────────────────────────
print(json.dumps({"status": "loading"}), flush=True)

from retriever import _get_embedding_model, _get_rerank_model
_get_embedding_model()
_get_rerank_model()

from graph import build_graph
from llm   import get_llm
from langchain_core.prompts import ChatPromptTemplate

graph = build_graph()

# ── 대화 상태 ──────────────────────────────────────────────────────────────────
summary: str        = ""   # 압축된 과거 대화 요약
history: list[dict] = []   # 최근 KEEP_RECENT개 메시지 ({"role", "content"})


# ── 파일 I/O ───────────────────────────────────────────────────────────────────

def _load_history():
    global summary, history
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data    = json.load(f)
                summary = data.get("summary", "")
                history = data.get("history", [])
        except Exception:
            summary, history = "", []


def _save_history():
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "history": history}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── 요약 ───────────────────────────────────────────────────────────────────────

_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """\
아래 대화를 핵심만 bullet 3~5줄로 요약하세요.
무엇을 물어봤고 어떤 결론이 나왔는지 위주로 작성하세요.
기존 요약이 있으면 합쳐서 하나의 요약으로 만드세요.\
"""),
    ("human", "{content}"),
])


def _summarize(old_summary: str, messages: list[dict]) -> str:
    content = ""
    if old_summary:
        content += f"[기존 요약]\n{old_summary}\n\n"
    content += "[대화]\n"
    for msg in messages:
        role = "사용자" if msg["role"] == "user" else "어시스턴트"
        content += f"{role}: {msg['content']}\n"
    chain  = _SUMMARY_PROMPT | get_llm()
    result = chain.invoke({"content": content})
    return result.content.strip()


def _maybe_summarize():
    global summary, history
    if len(history) <= HISTORY_LIMIT:
        return
    to_compress = history[:-KEEP_RECENT]
    print(json.dumps({"status": "이전 대화 요약 중..."}), flush=True)
    summary = _summarize(summary, to_compress)
    history = history[-KEEP_RECENT:]
    _save_history()


# ── 출처 추출 ──────────────────────────────────────────────────────────────────

def _sources(context: list[dict]) -> list[dict]:
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


# ── 시작 ───────────────────────────────────────────────────────────────────────

_load_history()
print(json.dumps({
    "status":      "ready",
    "has_history": bool(summary or history),
    "turns":       len(history) // 2,
}), flush=True)


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
        summary, history = "", []
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
        print(json.dumps({"done": True}), flush=True)
        continue

    question   = req.get("question", "")
    collection = req.get("collection", DEFAULT_COL)
    top_k      = int(req.get("top_k", 5))
    alpha      = float(req.get("alpha", 0.4))

    if not question:
        continue

    try:
        # 필요 시 요약 압축
        _maybe_summarize()

        # summary를 특수 롤로 history 앞에 붙여서 전달
        effective_history = []
        if summary:
            effective_history.append({"role": "summary", "content": f"[이전 대화 요약]\n{summary}"})
        effective_history.extend(history)

        initial_state = {
            "question":   question,
            "collection": collection,
            "top_k":      top_k,
            "alpha":      alpha,
            "history":    effective_history,
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

        # 히스토리 누적 및 저장
        history.append({"role": "user",      "content": question})
        history.append({"role": "assistant", "content": "".join(answer_parts)})
        _save_history()

        print(json.dumps({"sources": _sources(context)}), flush=True)
        print(json.dumps({"done": True}), flush=True)

    except Exception as e:
        print(json.dumps({"error": str(e)}), flush=True)
        print(json.dumps({"done": True}), flush=True)
