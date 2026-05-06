"""
Tauri 앱에서 호출하는 단일 검색 스크립트
결과를 JSON으로 stdout에 출력합니다.

사용법:
    python search_once.py "검색어" [top_k]
"""

import sys
import json
import os
from dotenv import load_dotenv

load_dotenv()

VECTOR_DB_PATH  = os.getenv("VECTOR_DB_PATH", "./vector_db")
COLLECTION_NAME = os.getenv("VECTOR_DB_COLLECTION", "confluence")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "검색어를 입력하세요", "results": []}, ensure_ascii=False))
        return

    query = sys.argv[1]
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        client     = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        collection = client.get_collection(COLLECTION_NAME)
        model      = SentenceTransformer(EMBEDDING_MODEL)

        embedding = model.encode([query]).tolist()
        results   = collection.query(
            query_embeddings=embedding,
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        hits = [
            {
                "document": doc,
                "metadata": meta,
                "score":    round(1 - dist, 4),
            }
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]
        print(json.dumps({"results": hits}, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"error": str(e), "results": []}, ensure_ascii=False))


if __name__ == "__main__":
    main()
