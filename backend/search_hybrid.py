"""
BM25 + Vector 하이브리드 검색 스크립트 (RRF 융합)
기존 search.py(벡터 전용)와 독립적으로 동작합니다.

의존성 추가 필요:
    pip install rank-bm25 konlpy

사용법:
    python search_hybrid.py

RRF 공식: score = Σ 1 / (k + rank_i)
  - k=60: 표준 smoothing 값 (원 논문 기준)
  - alpha: 벡터/BM25 가중치 비율 (0=BM25만, 1=벡터만)
    · 0.5  — 균등 (기본값, Weaviate 기본)
    · 0.75 — 벡터 편향 (LlamaIndex 기본, 의미 쿼리 많을 때)
    · 0.4  — BM25 편향 (고유명사/코드 쿼리 많을 때) ← 사내 위키 권장

쿼리 패턴별 추천 alpha:
  - "VPN 설정 방법" 같은 의미 쿼리 → alpha 높게 (0.6~0.75)
  - "192.168.1.5", "강태민", "PLAT-123" 같은 키워드 쿼리 → alpha 낮게 (0.3~0.4)
"""

import os
import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# 형태소 분석기 (설치 시 사용, 없으면 공백 분리로 폴백)
try:
    from konlpy.tag import Okt
    _okt = Okt()
    def tokenize(text: str) -> list[str]:
        return _okt.morphs(text, norm=True, stem=True)
except ImportError:
    _okt = None
    def tokenize(text: str) -> list[str]:
        return text.split()

load_dotenv()

VECTOR_DB_PATH  = os.getenv("VECTOR_DB_PATH", "./vector_db")
COLLECTION_NAME = os.getenv("VECTOR_DB_COLLECTION", "confluence")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")

# ── RRF 파라미터 ──────────────────────────────────────────────────────────────
RRF_K  = 60    # 표준 smoothing 값
ALPHA  = 0.4   # 사내 위키 권장: BM25 편향 (고유명사/IP/이름 쿼리 많음)
                # 의미 쿼리 위주라면 0.6~0.75로 올릴 것
TOP_K  = 5


# ── RRF 융합 ─────────────────────────────────────────────────────────────────

def rrf_score(rank: int, k: int = RRF_K) -> float:
    return 1.0 / (k + rank)


def reciprocal_rank_fusion(
    vector_hits: list[dict],
    bm25_hits: list[dict],
    alpha: float = ALPHA,
) -> list[dict]:
    """
    두 랭킹 결과를 RRF로 합산합니다.
    alpha: 벡터 검색 가중치 (1-alpha: BM25 가중치)
    """
    scores: dict[str, float] = {}
    docs:   dict[str, dict]  = {}

    # 벡터 검색 기여
    for rank, hit in enumerate(vector_hits):
        uid = hit["id"]
        scores[uid] = scores.get(uid, 0) + alpha * rrf_score(rank)
        docs[uid]   = hit

    # BM25 기여
    for rank, hit in enumerate(bm25_hits):
        uid = hit["id"]
        scores[uid] = scores.get(uid, 0) + (1 - alpha) * rrf_score(rank)
        docs[uid]   = hit

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {**docs[uid], "rrf_score": score}
        for uid, score in ranked[:TOP_K]
    ]


# ── BM25 인덱스 빌드 ──────────────────────────────────────────────────────────

def build_bm25_index(collection) -> tuple[BM25Okapi, list[dict]]:
    """ChromaDB에서 전체 문서를 가져와 BM25 인덱스 빌드."""
    print("BM25 인덱스 빌드 중...", end=" ", flush=True)

    result = collection.get(include=["documents", "metadatas"])
    ids       = result["ids"]
    documents = result["documents"]
    metadatas = result["metadatas"]

    corpus_tokens = [tokenize(doc) for doc in documents]
    bm25 = BM25Okapi(corpus_tokens)

    all_docs = [
        {"id": uid, "document": doc, "metadata": meta}
        for uid, doc, meta in zip(ids, documents, metadatas)
    ]

    tokenizer_name = "Okt 형태소 분석기" if _okt else "공백 분리 (konlpy 미설치)"
    print(f"완료 ({len(all_docs)}개 청크, {tokenizer_name})")
    return bm25, all_docs


# ── 검색 ─────────────────────────────────────────────────────────────────────

def vector_search(query: str, collection, model) -> list[dict]:
    embedding = model.encode([query]).tolist()
    results   = collection.query(
        query_embeddings=embedding,
        n_results=min(TOP_K * 3, collection.count()),  # RRF용으로 넉넉히
        include=["documents", "metadatas", "distances"],
    )
    return [
        {
            "id":       uid,
            "document": doc,
            "metadata": meta,
            "score":    1 - dist,
        }
        for uid, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]


def bm25_search(query: str, bm25: BM25Okapi, all_docs: list[dict]) -> list[dict]:
    tokens = tokenize(query)
    scores = bm25.get_scores(tokens)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    return [
        {**all_docs[i], "score": score}
        for i, score in ranked[:TOP_K * 3]
        if score > 0
    ]


# ── 출력 ─────────────────────────────────────────────────────────────────────

def print_result(i: int, hit: dict):
    meta = hit["metadata"]
    print(f"\n{'─' * 60}")
    print(f"[{i}] {meta.get('title', '제목 없음')}  (RRF 점수: {hit['rrf_score']:.4f})")
    print(f"    경로: {meta.get('breadcrumb', '')}")
    print(f"    URL : {meta.get('url', '')}")
    print(f"    수정: {meta.get('last_modified', '')[:10]}  버전: {meta.get('version', '')}")
    print()
    print(hit["document"].strip())


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    print("=== Confluence 하이브리드 검색 (Vector + BM25 / RRF) ===")
    print(f"alpha={ALPHA}  (벡터 {int(ALPHA*100)}% / BM25 {int((1-ALPHA)*100)}%)  |  RRF k={RRF_K}\n")

    try:
        client     = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        collection = client.get_collection(COLLECTION_NAME)
    except Exception as e:
        print(f"[오류] 벡터 DB 로드 실패: {e}")
        print("embed_pages.py를 먼저 실행하세요.")
        return

    total = collection.count()
    print(f"총 {total}개 청크 로드됨\n")

    print(f"임베딩 모델 로드 중: {EMBEDDING_MODEL} ...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    bm25, all_docs = build_bm25_index(collection)

    print("\n준비 완료. 검색어를 입력하세요. (종료: q 또는 빈 입력)\n")
    print(f"  alpha 조정: 쿼리 앞에 '@0.7' 형식으로 입력 (예: @0.7 재택근무 정책)")
    print(f"  현재 alpha={ALPHA} (높을수록 벡터 편향, 낮을수록 BM25 편향)\n")

    current_alpha = ALPHA

    while True:
        try:
            raw = input("검색 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if not raw or raw.lower() == "q":
            print("종료합니다.")
            break

        # alpha 인라인 조정: "@0.7 쿼리내용"
        if raw.startswith("@"):
            parts = raw.split(maxsplit=1)
            try:
                current_alpha = float(parts[0][1:])
                raw = parts[1] if len(parts) > 1 else ""
                print(f"  → alpha 변경: {current_alpha}")
            except (ValueError, IndexError):
                print("  alpha 형식 오류. 예: @0.7 검색어")
                continue

        query = raw
        if not query:
            continue

        v_hits   = vector_search(query, collection, model)
        b_hits   = bm25_search(query, bm25, all_docs)
        combined = reciprocal_rank_fusion(v_hits, b_hits, alpha=current_alpha)

        if not combined:
            print("결과가 없습니다.")
            continue

        print(f"\n'{query}' 하이브리드 검색 결과 (alpha={current_alpha}, 상위 {len(combined)}개):")
        for i, hit in enumerate(combined, 1):
            print_result(i, hit)
        print(f"\n{'═' * 60}")


if __name__ == "__main__":
    main()
