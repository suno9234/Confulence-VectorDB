"""
Tauri 앱에서 호출하는 단일 검색 스크립트
결과를 JSON으로 stdout에 출력합니다.

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
        from retriever import search, rerank, fetch_all_chunks_for_pages, RERANK_FETCH_K, RERANK_THRESHOLD

        # 1. 후보 20개 검색 → 리랭킹 → 상위 top_k 페이지 선택
        hits = search(query=query, collection_name=collection_name, top_k=RERANK_FETCH_K, alpha=alpha)
        hits = rerank(query, hits)

        # 2. 페이지별 최고 점수 기록: rerank로 선택, RRF는 표시용
        page_rerank: dict = {}
        page_rrf:    dict = {}
        page_vscores: dict = {}
        page_bscores: dict = {}
        for hit in hits:
            pid    = hit["metadata"].get("page_id", "")
            rscore = hit.get("rerank_score", hit["score"])
            if pid and rscore > page_rerank.get(pid, float("-inf")):
                page_rerank[pid]  = rscore
                page_rrf[pid]     = hit["score"]
                page_vscores[pid] = hit.get("vector_score")
                page_bscores[pid] = hit.get("bm25_score")
        page_rerank  = {pid: s for pid, s in page_rerank.items() if s > RERANK_THRESHOLD}
        sorted_pages = sorted(page_rerank.items(), key=lambda x: x[1], reverse=True)[:top_k]
        page_rerank  = dict(sorted_pages)
        page_rrf     = {pid: s for pid, s in page_rrf.items()     if pid in page_rerank}
        page_vscores = {pid: v for pid, v in page_vscores.items() if pid in page_rerank}
        page_bscores = {pid: b for pid, b in page_bscores.items() if pid in page_rerank}

        # 3. 해당 페이지의 전체 청크 조회
        all_chunks = fetch_all_chunks_for_pages(list(page_rerank.keys()), collection_name)

        # 4. 각 청크에 표시용 RRF + 정렬용 rerank_score 부여
        for chunk in all_chunks:
            pid = chunk["metadata"].get("page_id", "")
            chunk["score"]        = page_rrf.get(pid, 0.0)
            chunk["rerank_score"] = page_rerank.get(pid, 0.0)
            chunk["vector_score"] = page_vscores.get(pid)
            chunk["bm25_score"]   = page_bscores.get(pid)

        print(json.dumps({"results": all_chunks}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e), "results": []}, ensure_ascii=False))


if __name__ == "__main__":
    main()
