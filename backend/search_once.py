"""
Tauri 앱에서 호출하는 단일 검색 스크립트 (Vector + BM25 하이브리드 RRF)
결과를 JSON으로 stdout에 출력합니다.

사용법:
    python search_once.py "검색어" [top_k] [collection] [alpha]
    alpha: 0.0=BM25전용 ~ 1.0=벡터전용 (기본값 0.4)
"""

import sys
import json
import os
from dotenv import load_dotenv
load_dotenv()

VECTOR_DB_PATH  = os.getenv("VECTOR_DB_PATH", "./vector_db")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", "50"))
COLLECTION_NAME = f"{os.getenv('VECTOR_DB_COLLECTION', 'confluence')}_{CHUNK_SIZE}_{CHUNK_OVERLAP}"
RRF_K           = 60


def build_bm25(collection):
    from rank_bm25 import BM25Okapi
    data      = collection.get(include=["documents", "metadatas"])
    all_docs  = [
        {"id": uid, "document": doc, "metadata": meta}
        for uid, doc, meta in zip(data["ids"], data["documents"], data["metadatas"])
    ]
    corpus = [doc.split() for doc in data["documents"]]
    return BM25Okapi(corpus), all_docs


def vector_search(query, collection, model, n):
    emb = model.encode([query]).tolist()
    res = collection.query(
        query_embeddings=emb,
        n_results=min(n, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    return [
        {"id": uid, "document": doc, "metadata": meta, "score": 1 - dist}
        for uid, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0],
            res["metadatas"][0], res["distances"][0],
        )
    ]


def bm25_search(query, bm25, all_docs, n):
    scores = bm25.get_scores(query.split())
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:n]
    return [
        {**all_docs[i], "score": float(score)}
        for i, score in ranked if score > 0
    ]


def rrf_fusion(v_hits, b_hits, alpha, top_k):
    scores, docs, v_scores, b_scores = {}, {}, {}, {}
    for rank, hit in enumerate(v_hits):
        uid = hit["id"]
        scores[uid]  = scores.get(uid, 0) + alpha * (1.0 / (RRF_K + rank))
        docs[uid]    = hit
        v_scores[uid] = round(hit["score"], 4)
    for rank, hit in enumerate(b_hits):
        uid = hit["id"]
        scores[uid]  = scores.get(uid, 0) + (1 - alpha) * (1.0 / (RRF_K + rank))
        docs[uid]    = hit
        b_scores[uid] = round(hit["score"], 2)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        {
            "document":     docs[uid]["document"],
            "metadata":     docs[uid]["metadata"],
            "score":        round(rrf, 4),
            "vector_score": v_scores.get(uid),
            "bm25_score":   b_scores.get(uid),
        }
        for uid, rrf in ranked
    ]


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == '--list':
        try:
            import chromadb
            client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
            names  = sorted(client.list_collections())
            print(json.dumps({"collections": names}, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"collections": [], "error": str(e)}, ensure_ascii=False))
        return

    if len(sys.argv) >= 3 and sys.argv[1] == '--delete':
        try:
            import chromadb
            client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
            client.delete_collection(sys.argv[2])
            print(json.dumps({"ok": True}, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return

    if len(sys.argv) < 2:
        print(json.dumps({"error": "검색어를 입력하세요", "results": []}, ensure_ascii=False))
        return

    query           = sys.argv[1]
    top_k           = int(sys.argv[2])   if len(sys.argv) > 2 else 5
    collection_name = sys.argv[3]        if len(sys.argv) > 3 else COLLECTION_NAME
    alpha           = float(sys.argv[4]) if len(sys.argv) > 4 else 0.4

    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        client     = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        collection = client.get_collection(collection_name)
        model      = SentenceTransformer(EMBEDDING_MODEL)

        fetch_n = top_k * 3

        if alpha >= 1.0:
            raw = vector_search(query, collection, model, top_k)
            hits = [{"document": h["document"], "metadata": h["metadata"],
                     "score": round(h["score"], 4),
                     "vector_score": round(h["score"], 4), "bm25_score": None}
                    for h in raw]
        elif alpha <= 0.0:
            bm25, all_docs = build_bm25(collection)
            raw = bm25_search(query, bm25, all_docs, top_k)
            hits = [{"document": h["document"], "metadata": h["metadata"],
                     "score": round(h["score"], 2),
                     "vector_score": None, "bm25_score": round(h["score"], 2)}
                    for h in raw]
        else:
            bm25, all_docs = build_bm25(collection)
            v_hits = vector_search(query, collection, model, fetch_n)
            b_hits = bm25_search(query, bm25, all_docs, fetch_n)
            hits   = rrf_fusion(v_hits, b_hits, alpha, top_k)

        print(json.dumps({"results": hits}, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"error": str(e), "results": []}, ensure_ascii=False))


if __name__ == "__main__":
    main()
