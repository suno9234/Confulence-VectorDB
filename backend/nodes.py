"""
nodes.py — LangGraph 파이프라인 노드 함수 정의

각 노드는 State를 입력받아 업데이트할 필드만 dict로 반환한다.
파이프라인 흐름: refine_node → retrieve_node → generate_node
"""

from typing import TypedDict

from retriever import search, rerank, fetch_all_chunks_for_pages, COLLECTION_NAME, RERANK_FETCH_K, RERANK_THRESHOLD
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
    정제 쿼리로 하이브리드 검색 후 cross-encoder 리랭킹을 거쳐 관련 페이지 청크를 반환.

    처리 순서:
    1. RERANK_FETCH_K(=20)개 후보 청크 검색 (BM25 + 벡터 RRF)
    2. cross-encoder로 리랭킹 → rerank_score 부여
    3. RERANK_THRESHOLD 미만 페이지 제거
    4. rerank_score 기준 상위 top_k 페이지 선정
    5. 선정된 페이지의 전체 청크 조회 (LLM에게 잘린 청크가 아닌 전체 문서 제공)
    """
    top_k    = state.get("top_k", 5)
    col_name = state.get("collection") or COLLECTION_NAME

    query = state.get("refined_query") or state["question"]
    hits  = search(
        query           = query,
        collection_name = col_name,
        top_k           = RERANK_FETCH_K,   # 리랭킹 전 충분한 후보 확보
        alpha           = state.get("alpha", 0.4),
    )
    hits = rerank(query, hits)

    # 페이지별 최고 점수 집계: rerank_score로 필터링·정렬, RRF score는 UI 표시용으로 보존
    page_rerank: dict[str, float] = {}  # page_id → rerank_score (정렬·필터 기준)
    page_rrf:    dict[str, float] = {}  # page_id → RRF score (UI 표시용)
    for hit in hits:
        pid    = hit["metadata"].get("page_id", "")
        rscore = hit.get("rerank_score", hit["score"])
        if pid and rscore > page_rerank.get(pid, float("-inf")):
            page_rerank[pid] = rscore
            page_rrf[pid]    = hit["score"]

    # 임계값 필터: 관련성 낮은 페이지 제거 (단, 결과가 전혀 없으면 1위 페이지는 유지)
    page_rerank = {pid: s for pid, s in page_rerank.items() if s > RERANK_THRESHOLD}
    if not page_rerank and hits:
        pid = hits[0]["metadata"].get("page_id", "")
        page_rerank = {pid: hits[0].get("rerank_score", 0.0)}

    # rerank_score 내림차순으로 상위 top_k 페이지만 유지
    sorted_pages = sorted(page_rerank.items(), key=lambda x: x[1], reverse=True)[:top_k]
    page_rerank  = dict(sorted_pages)
    page_rrf     = {pid: s for pid, s in page_rrf.items() if pid in page_rerank}

    # 선정된 페이지의 모든 청크 조회 후 점수 복원
    all_chunks = fetch_all_chunks_for_pages(list(page_rerank.keys()), col_name)
    for chunk in all_chunks:
        pid = chunk["metadata"].get("page_id", "")
        chunk["score"]        = page_rrf.get(pid, 0.0)      # UI 표시용 RRF 점수
        chunk["rerank_score"] = page_rerank.get(pid, 0.0)   # 정렬용 rerank 점수

    return {"context": all_chunks}


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
