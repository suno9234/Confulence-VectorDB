"""
graph.py — LangGraph 파이프라인 조립

노드 연결과 실행 순서만 정의한다. 각 노드의 로직은 nodes.py에 있다.
파이프라인: refine → retrieve → generate → END
"""

from langgraph.graph import StateGraph, END
from nodes import State, refine_node, retrieve_node, generate_node


def build_graph():
    """노드를 순서대로 연결한 컴파일된 LangGraph 그래프를 반환."""
    g = StateGraph(State)

    g.add_node("refine",   refine_node)    # 질문 → 검색 쿼리 정제
    g.add_node("retrieve", retrieve_node)  # 하이브리드 검색 + 리랭킹
    g.add_node("generate", generate_node)  # RAG 답변 생성

    g.set_entry_point("refine")
    g.add_edge("refine",   "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)

    return g.compile()
