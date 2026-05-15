"""
search_once.py — Tauri 앱에서 호출하는 단일 검색 스크립트

결과를 JSON으로 stdout에 출력한다.

사용법:
    python search_once.py "검색어" [top_k] [collection] [alpha]
    python search_once.py --list
    python search_once.py --delete <collection>
"""

import sys
import json
import os
from dotenv import load_dotenv
load_dotenv()

VECTOR_DB_PATH  = os.getenv("VECTOR_DB_PATH", "./vector_db")
CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", "50"))
COLLECTION_NAME = f"{os.getenv('VECTOR_DB_COLLECTION', 'confluence')}_{CHUNK_SIZE}_{CHUNK_OVERLAP}"


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--list":
        try:
            import chromadb
            client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
            names  = sorted(client.list_collections())
            print(json.dumps({"collections": names}, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"collections": [], "error": str(e)}, ensure_ascii=False))
        return

    if len(sys.argv) >= 3 and sys.argv[1] == "--delete":
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
        from retriever import search_rerank_fetch

        chunks = search_rerank_fetch(
            query           = query,
            collection_name = collection_name,
            top_k           = top_k,
            alpha           = alpha,
        )
        print(json.dumps({"results": chunks}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e), "results": []}, ensure_ascii=False))


if __name__ == "__main__":
    main()
