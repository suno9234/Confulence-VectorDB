"""
chat.py — Tauri 앱에서 호출하는 챗봇 진입점

Tauri의 run_chat 커맨드가 이 스크립트를 subprocess로 실행한다.
사용법:
    python chat.py "질문" [collection] [top_k] [alpha] [--stream]

출력 형식 (JSON Lines, stdout):
    --stream 모드:
        {"status": "검색 중..."}   → 진행 상태 메시지 (UI 상태 표시용)
        {"t": "토큰"}              → LLM 생성 토큰 (스트리밍)
        {"sources": [...]}         → 참고 문서 목록
        {"done": true}             → 스트리밍 완료 신호
    invoke 모드 (--stream 없을 때):
        {"answer": "...", "sources": [...]}  → 전체 답변 한 줄
"""

import sys
import json
import os
from dotenv import load_dotenv
load_dotenv()

# 컬렉션명 기본값: embed_pages.py와 동일한 규칙으로 생성 (collection_청크크기_오버랩)
CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
DEFAULT_COL   = f"{os.getenv('VECTOR_DB_COLLECTION', 'confluence')}_{CHUNK_SIZE}_{CHUNK_OVERLAP}"


def _sources(context: list[dict]) -> list[dict]:
    """청크 목록에서 페이지별 출처 정보(제목·URL·breadcrumb)를 중복 없이 추출."""
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


def main():
    # CLI 인자 파싱: 위치 인자와 --flag 분리
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags      = {a for a in sys.argv[1:] if a.startswith("--")}

    if not positional:
        print(json.dumps({"error": "질문을 입력하세요"}, ensure_ascii=False))
        return

    question   = positional[0]
    collection = positional[1] if len(positional) > 1 else DEFAULT_COL
    top_k      = int(positional[2])   if len(positional) > 2 else 5
    alpha      = float(positional[3]) if len(positional) > 3 else 0.4
    streaming  = "--stream" in flags

    try:
        from graph import build_graph

        graph = build_graph()
        initial_state = {
            "question":   question,
            "collection": collection,
            "top_k":      top_k,
            "alpha":      alpha,
        }

        if streaming:
            context = []
            # stream_mode=["messages","updates"]: messages=LLM 토큰, updates=노드 완료 이벤트
            for mode, data in graph.stream(initial_state, stream_mode=["messages", "updates"]):
                if mode == "updates":
                    # 각 노드 완료 시점에 UI에 진행 상태 전송
                    if "refine" in data:
                        refined_q = data["refine"].get("refined_query", "")
                        print(json.dumps({"status": f"검색 중... ({refined_q})"}, ensure_ascii=False), flush=True)
                    elif "retrieve" in data:
                        context  = data["retrieve"].get("context", [])
                        page_cnt = len({c["metadata"].get("page_id") for c in context})
                        print(json.dumps({"status": f"{page_cnt}개 문서 분석 중..."}, ensure_ascii=False), flush=True)
                    elif "generate" in data:
                        print(json.dumps({"status": ""}, ensure_ascii=False), flush=True)  # 상태 메시지 제거
                elif mode == "messages":
                    msg, metadata = data
                    if metadata.get("langgraph_node") != "generate":
                        continue  # generate 노드 토큰만 스트리밍 (refine LLM 출력 제외)
                    if hasattr(msg, "content") and msg.content:
                        content = msg.content
                        if isinstance(content, str):
                            print(json.dumps({"t": content}, ensure_ascii=False), flush=True)
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    print(json.dumps({"t": block["text"]}, ensure_ascii=False), flush=True)

            print(json.dumps({"sources": _sources(context)}, ensure_ascii=False), flush=True)
            print(json.dumps({"done": True}, ensure_ascii=False), flush=True)

        else:
            result = graph.invoke(initial_state)
            print(json.dumps({
                "answer":  result["answer"],
                "sources": _sources(result["context"]),
            }, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
