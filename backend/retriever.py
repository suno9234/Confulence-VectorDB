"""
retriever.py — 하이브리드 검색 엔진 (벡터 + BM25 + 리랭킹)

검색 탭(search_once.py)과 챗봇 파이프라인(nodes.py) 양쪽에서 공통으로 사용한다.
검색 흐름: 벡터 검색 + BM25F 검색 → RRF 통합 → cross-encoder 리랭킹
"""

import os
from dotenv import load_dotenv
load_dotenv()

# ── ChromaDB 경로 및 컬렉션 설정 ──────────────────────────────────────────────
VECTOR_DB_PATH  = os.getenv("VECTOR_DB_PATH",  "./vector_db")   # ChromaDB 저장 디렉터리
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")  # 벡터 임베딩 모델
CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE",    "500"))         # 임베딩 당시 청크 크기 (컬렉션명에 포함)
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", "50"))          # 임베딩 당시 청크 오버랩 (컬렉션명에 포함)
COLLECTION_NAME = f"{os.getenv('VECTOR_DB_COLLECTION', 'confluence')}_{CHUNK_SIZE}_{CHUNK_OVERLAP}"

# ── RRF 파라미터 ───────────────────────────────────────────────────────────────
RRF_K = 60  # RRF 공식의 상수 k. 클수록 순위 차이 영향이 줄어듦 (일반적으로 60 고정)

# ── BM25F 필드 가중치 ──────────────────────────────────────────────────────────
BM25_TITLE_WEIGHT      = 3.0  # 제목 BM25 점수에 곱하는 가중치 (본문 대비 중요도 높음)
BM25_BREADCRUMB_WEIGHT = 1.5  # breadcrumb BM25 점수에 곱하는 가중치

# ── 리랭킹 설정 ───────────────────────────────────────────────────────────────
RERANK_MODEL     = os.getenv("RERANK_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")  # cross-encoder 모델명
RERANK_FETCH_K   = int(os.getenv("RERANK_FETCH_K",   "20"))    # 리랭킹 전 초기 후보 청크 수
RERANK_THRESHOLD = float(os.getenv("RERANK_THRESHOLD", "-1.0")) # 리랭킹 점수(로짓) 하한선. 이 값 미만 페이지는 제외


def get_collection(collection_name: str | None = None):
    """ChromaDB에서 지정한 컬렉션을 열어 반환."""
    import chromadb
    client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
    return client.get_collection(collection_name or COLLECTION_NAME)


def fetch_all_chunks_for_pages(page_ids: list[str], collection_name: str | None = None) -> list[dict]:
    """page_id 목록에 속하는 모든 청크를 ChromaDB에서 조회."""
    if not page_ids:
        return []
    collection = get_collection(collection_name)
    result = collection.get(
        where={"page_id": {"$in": page_ids}},
        include=["documents", "metadatas"],
    )
    return [
        {"document": doc, "metadata": meta, "score": 0.0}
        for doc, meta in zip(result["documents"], result["metadatas"])
    ]


def build_bm25(collection):
    """
    컬렉션 전체 문서를 읽어 BM25 인덱스 3개(본문·제목·breadcrumb)와 전체 문서 목록을 반환.
    BM25F: 필드별로 별도 인덱스를 만들고 검색 시 가중치 합산하는 방식.
    """
    from rank_bm25 import BM25Okapi
    data     = collection.get(include=["documents", "metadatas"])
    all_docs = [
        {"id": uid, "document": doc, "metadata": meta}
        for uid, doc, meta in zip(data["ids"], data["documents"], data["metadatas"])
    ]

    def _strip_root(bc: str) -> str:
        # breadcrumb 첫 항목(위키 루트명)을 제거해 모든 페이지에 공통으로 등장하는 노이즈를 줄임
        parts = bc.split(" > ")
        return " > ".join(parts[1:]) if len(parts) > 1 else ""

    body_corpus       = [doc.lower().split() for doc in data["documents"]]
    title_corpus      = [meta.get("title", "").lower().split() for meta in data["metadatas"]]
    breadcrumb_corpus = [_strip_root(meta.get("breadcrumb", "")).lower().split() for meta in data["metadatas"]]
    return BM25Okapi(body_corpus), BM25Okapi(title_corpus), BM25Okapi(breadcrumb_corpus), all_docs


def vector_search(query: str, collection, model, n: int) -> list[dict]:
    """쿼리를 임베딩해 ChromaDB에서 코사인 유사도 기준 상위 n개 청크 반환."""
    emb = model.encode([query]).tolist()
    res = collection.query(
        query_embeddings=emb,
        n_results=min(n, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    return [
        {"id": uid, "document": doc, "metadata": meta, "score": 1 - dist}  # 거리 → 유사도 변환
        for uid, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0],
            res["metadatas"][0], res["distances"][0],
        )
    ]


def bm25_search(query: str, bm25_body, bm25_title, bm25_breadcrumb, all_docs: list, n: int) -> list[dict]:
    """
    BM25F 검색: 본문·제목·breadcrumb 점수를 정규화 후 가중치 합산해 상위 n개 반환.
    필드별 정규화(_norm)를 거쳐야 스케일 차이로 인한 점수 왜곡을 방지할 수 있음.
    """
    import numpy as np

    def _norm(arr):
        # 각 필드 점수를 최댓값으로 나눠 0~1 범위로 정규화
        m = arr.max()
        return arr / m if m > 0 else arr

    tokens            = query.lower().split()
    body_scores       = _norm(np.array(bm25_body.get_scores(tokens)))
    title_scores      = _norm(np.array(bm25_title.get_scores(tokens)))
    breadcrumb_scores = _norm(np.array(bm25_breadcrumb.get_scores(tokens)))
    combined          = body_scores + BM25_TITLE_WEIGHT * title_scores + BM25_BREADCRUMB_WEIGHT * breadcrumb_scores
    ranked            = sorted(enumerate(combined), key=lambda x: x[1], reverse=True)[:n]
    return [
        {**all_docs[i], "score": float(score)}
        for i, score in ranked if score > 0
    ]


def rrf_fusion(v_hits: list, b_hits: list, alpha: float, top_k: int) -> list[dict]:
    """
    Reciprocal Rank Fusion: 벡터 순위와 BM25 순위를 통합해 최종 점수 산출.
    alpha=1.0 → 벡터 전용 / alpha=0.0 → BM25 전용 / 중간값 → 두 순위 혼합.
    반환값의 score는 RRF 통합 점수(표시용), vector_score·bm25_score는 개별 점수.
    """
    scores, docs, v_scores, b_scores = {}, {}, {}, {}
    for rank, hit in enumerate(v_hits):
        uid = hit["id"]
        scores[uid]   = scores.get(uid, 0) + alpha * (1.0 / (RRF_K + rank))
        docs[uid]     = hit
        v_scores[uid] = round(hit["score"], 4)
    for rank, hit in enumerate(b_hits):
        uid = hit["id"]
        scores[uid]   = scores.get(uid, 0) + (1 - alpha) * (1.0 / (RRF_K + rank))
        docs[uid]     = hit
        b_scores[uid] = round(hit["score"], 2)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        {
            "document":     docs[uid]["document"],
            "metadata":     docs[uid]["metadata"],
            "score":        round(rrf, 4),   # RRF 통합 점수 (UI 표시용)
            "vector_score": v_scores.get(uid),
            "bm25_score":   b_scores.get(uid),
        }
        for uid, rrf in ranked
    ]


def rerank(query: str, hits: list[dict]) -> list[dict]:
    """
    cross-encoder로 (쿼리, 문서) 쌍을 재평가해 rerank_score 추가 후 내림차순 정렬.
    입력 문서는 breadcrumb + 제목 + 본문을 합쳐 문맥을 최대한 제공.
    rerank_score는 로짓값(범위 제한 없음): 0 이상이면 관련, -2~0이면 경계, -5 이하면 무관련.
    """
    from sentence_transformers import CrossEncoder
    model = CrossEncoder(RERANK_MODEL)
    pairs = [
        (query, f"{h['metadata'].get('breadcrumb', '')}\n{h['metadata'].get('title', '')}\n{h['document']}")
        for h in hits
    ]
    scores = model.predict(pairs)
    for hit, score in zip(hits, scores):
        hit["rerank_score"] = float(score)
    return sorted(hits, key=lambda x: x["rerank_score"], reverse=True)


def search(
    query:           str,
    collection_name: str | None = None,
    top_k:           int        = 5,
    alpha:           float      = 0.4,
    vector_query:    str | None = None,
) -> list[dict]:
    """
    하이브리드 검색 수행 후 청크 목록 반환 (리랭킹 미포함, 검색 탭에서 직접 사용).
    query        : BM25 키워드 검색에 사용 (정제된 쿼리 권장)
    vector_query : 벡터 검색에 사용 (없으면 query 그대로 사용)
    alpha=1.0 → 벡터 전용 / alpha=0.0 → BM25 전용 / 중간 → RRF 혼합
    """
    from sentence_transformers import SentenceTransformer

    collection = get_collection(collection_name)
    model      = SentenceTransformer(EMBEDDING_MODEL)
    fetch_n    = top_k * 3  # RRF 통합 품질을 위해 각 방법에서 top_k보다 많이 수집
    v_query    = vector_query or query

    if alpha >= 1.0:
        raw  = vector_search(v_query, collection, model, top_k)
        return [
            {"document": h["document"], "metadata": h["metadata"],
             "score": round(h["score"], 4),
             "vector_score": round(h["score"], 4), "bm25_score": None}
            for h in raw
        ]

    if alpha <= 0.0:
        bm25_body, bm25_title, bm25_breadcrumb, all_docs = build_bm25(collection)
        raw = bm25_search(query, bm25_body, bm25_title, bm25_breadcrumb, all_docs, top_k)
        return [
            {"document": h["document"], "metadata": h["metadata"],
             "score": round(h["score"], 2),
             "vector_score": None, "bm25_score": round(h["score"], 2)}
            for h in raw
        ]

    bm25_body, bm25_title, bm25_breadcrumb, all_docs = build_bm25(collection)
    v_hits = vector_search(v_query, collection, model, fetch_n)
    b_hits = bm25_search(query, bm25_body, bm25_title, bm25_breadcrumb, all_docs, fetch_n)
    return rrf_fusion(v_hits, b_hits, alpha, top_k)
