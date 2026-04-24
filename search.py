"""
벡터 DB 검색 테스트 스크립트
embed_pages.py 실행 후 생성된 vector_db/를 검색합니다.

사용법:
    python search.py
"""

import os
import chromadb
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

VECTOR_DB_PATH  = os.getenv("VECTOR_DB_PATH", "./vector_db")
COLLECTION_NAME = os.getenv("VECTOR_DB_COLLECTION", "confluence")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
TOP_K           = 5


def search(query: str, collection, model) -> list[dict]:
    embedding = model.encode([query]).tolist()
    results   = collection.query(
        query_embeddings=embedding,
        n_results=TOP_K,
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({"document": doc, "metadata": meta, "score": 1 - dist})
    return hits


def print_result(i: int, hit: dict):
    meta = hit["metadata"]
    print(f"\n{'─' * 60}")
    print(f"[{i}] {meta.get('title', '제목 없음')}  (점수: {hit['score']:.3f})")
    print(f"    경로: {meta.get('breadcrumb', '')}")
    print(f"    URL : {meta.get('url', '')}")
    print(f"    수정: {meta.get('last_modified', '')[:10]}  버전: {meta.get('version', '')}")
    if meta.get("labels"):
        print(f"    태그: {meta['labels']}")
    print()
    print(hit["document"].strip())


def main():
    print("=== Confluence 벡터 검색 ===")
    print(f"DB 경로: {VECTOR_DB_PATH}  |  컬렉션: {COLLECTION_NAME}\n")

    # ChromaDB 로드
    try:
        client     = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        collection = client.get_collection(COLLECTION_NAME)
    except Exception as e:
        print(f"[오류] 벡터 DB를 불러올 수 없습니다: {e}")
        print("embed_pages.py를 먼저 실행하세요.")
        return

    total = collection.count()
    print(f"총 {total}개 청크 로드됨\n")

    # 임베딩 모델 로드
    print(f"임베딩 모델 로드 중: {EMBEDDING_MODEL} ...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("준비 완료. 검색어를 입력하세요. (종료: q 또는 빈 입력)\n")

    while True:
        try:
            query = input("검색 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if not query or query.lower() == "q":
            print("종료합니다.")
            break

        hits = search(query, collection, model)

        if not hits:
            print("결과가 없습니다.")
            continue

        print(f"\n'{query}' 검색 결과 (상위 {len(hits)}개):")
        for i, hit in enumerate(hits, 1):
            print_result(i, hit)
        print(f"\n{'═' * 60}")


if __name__ == "__main__":
    main()
