"""
nodes.py — LangGraph 파이프라인 노드 함수 정의

각 노드는 State를 입력받아 업데이트할 필드만 dict로 반환한다.
파이프라인 흐름: refine_node → retrieve_node → generate_node
"""

from typing import TypedDict

from retriever import search_rerank_fetch, COLLECTION_NAME
from prompts   import REFINE_PROMPT, RAG_PROMPT
from llm       import get_llm


class State(TypedDict):
    """LangGraph 파이프라인 전체에서 공유되는 상태 객체."""
    question:       str        # 사용자의 원본 질문
    refined_query:  str        # refine_node가 생성한 검색용 정제 쿼리
    collection:     str        # 검색할 ChromaDB 컬렉션명
    top_k:          int        # 최종 참고할 페이지 수
    alpha:          float      # BM25·벡터 비율 (0=BM25 전용, 1=벡터 전용)
    context:        list[dict] # retrieve_node가 수집한 청크 목록
    answer:         str        # generate_node가 생성한 최종 답변


def refine_node(state: State) -> dict:
    """
    사용자 질문을 검색에 적합한 짧은 키워드 쿼리로 변환.
    구어체·문맥 제거 → 핵심 명사 위주 10단어 이내 텍스트 출력.
    """
    chain   = REFINE_PROMPT | get_llm()
    result  = chain.invoke({"question": state["question"]})
    refined = result.content.strip()
    return {"refined_query": refined or state["question"]}  # 빈 결과면 원본 질문 사용


def retrieve_node(state: State) -> dict:
    """
    정제 쿼리로 하이브리드 검색 + 리랭킹 + 페이지 선택 + 전체 청크 조회.
    세부 로직은 retriever.search_rerank_fetch()에 위임.
    """
    query    = state.get("refined_query") or state["question"]
    col_name = state.get("collection") or COLLECTION_NAME

    chunks = search_rerank_fetch(
        query           = query,
        collection_name = col_name,
        top_k           = state.get("top_k", 5),
        alpha           = state.get("alpha", 0.4),
    )
    return {"context": chunks}


def _aggregate_by_page(chunks: list[dict]) -> list[dict]:
    """
    청크 목록을 page_id 기준으로 묶어 페이지 단위 문서로 변환.
    청크는 chunk_index 오름차순으로 이어 붙여 원문 흐름을 유지한다.
    반환 목록은 rerank_score 내림차순 정렬.
    """
    pages = {}
    for chunk in chunks:
        pid = chunk["metadata"].get("page_id", chunk["metadata"].get("title", ""))
        if pid not in pages:
            pages[pid] = {"metadata": chunk["metadata"], "chunks": [], "score": chunk["score"]}
        pages[pid]["chunks"].append(chunk)
        if chunk["score"] > pages[pid]["score"]:
            pages[pid]["score"] = chunk["score"]

    result = []
    for page in pages.values():
        sorted_chunks = sorted(
            page["chunks"],
            key=lambda c: int(c["metadata"].get("chunk_index", 0)),
        )
        rerank_score = max((c.get("rerank_score", 0.0) for c in page["chunks"]), default=0.0)
        result.append({
            "metadata":     page["metadata"],
            "document":     "\n".join(c["document"] for c in sorted_chunks),
            "score":        page["score"],
            "rerank_score": rerank_score,
        })

    return sorted(result, key=lambda p: p["rerank_score"], reverse=True)


def generate_node(state: State) -> dict:
    """
    수집된 청크를 페이지 단위로 묶어 LLM에 전달하고 최종 답변을 생성.
    문서는 [제목] + 본문 형태로 구분자(---)와 함께 연결해 LLM에 제공.
    """
    pages        = _aggregate_by_page(state["context"])
    context_text = "\n\n---\n\n".join(
        f"[{p['metadata']['title']}]\n{p['document']}"
        for p in pages
    )
    chain    = RAG_PROMPT | get_llm()
    response = chain.invoke({
        "context":  context_text,
        "question": state["question"],
    })
    return {"answer": response.content}
