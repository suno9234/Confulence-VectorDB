"""
Confluence 페이지 임베딩 스크립트
Confluence REST API v1으로 전체 페이지(본문 + 메타데이터)를 수집하고
ChromaDB에 임베딩하여 저장합니다.

생성된 vector_db/ 폴더는 다른 프로젝트에서 아래처럼 바로 재사용 가능:
    import chromadb
    client     = chromadb.PersistentClient(path="./vector_db")
    collection = client.get_collection("confluence")
    results    = collection.query(query_embeddings=[...], n_results=5)

사용법:
    python embed_pages.py

.env 필수 항목:
    CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN, CONFLUENCE_SPACE_KEY
"""

import os
from dotenv import load_dotenv
load_dotenv()

import requests
import chromadb
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer

BASE_URL        = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
EMAIL           = os.environ["CONFLUENCE_EMAIL"]
TOKEN           = os.environ["CONFLUENCE_API_TOKEN"]
SPACE_KEY       = os.environ["CONFLUENCE_SPACE_KEY"]
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
VECTOR_DB_PATH  = os.getenv("VECTOR_DB_PATH", "./vector_db")
CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", "50"))
COLLECTION_NAME = f"{os.getenv('VECTOR_DB_COLLECTION', 'confluence')}_{CHUNK_SIZE}_{CHUNK_OVERLAP}"

AUTH    = (EMAIL, TOKEN)
HEADERS = {"Accept": "application/json"}


# ── Confluence API v1 (expand 지원으로 한 번에 모든 정보 수집) ─────────────────

def fetch_all_pages():
    """Space 내 모든 페이지를 페이지네이션으로 전부 수집합니다."""
    pages   = []
    start   = 0
    limit   = 50  # v1 API expand 사용 시 50 권장

    params_base = {
        "spaceKey": SPACE_KEY,
        "type":     "page",
        "status":   "current",
        "expand":   "ancestors,version,body.storage,metadata.labels",
        "limit":    limit,
    }

    while True:
        params = {**params_base, "start": start}
        resp   = requests.get(
            f"{BASE_URL}/wiki/rest/api/content",
            auth=AUTH, headers=HEADERS, params=params
        )
        resp.raise_for_status()
        data    = resp.json()
        results = data.get("results", [])
        pages.extend(results)

        print(f"  수집 중... 누적 {len(pages)}개 (이번 배치: {len(results)}개)")

        # _links.next 없으면 마지막 페이지
        if not data.get("_links", {}).get("next"):
            break
        start += limit

    return pages


# ── 텍스트 처리 ───────────────────────────────────────────────────────────────

def parse_html(html: str) -> str:
    """Confluence storage format(XHTML)에서 순수 텍스트 추출"""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator="\n", strip=True)


def chunk_text(text: str) -> list[str]:
    """텍스트를 CHUNK_SIZE 글자 단위로 분할 (CHUNK_OVERLAP 글자 overlap)"""
    chunks  = []
    start   = 0
    length  = len(text)

    while start < length:
        end = min(start + CHUNK_SIZE, length)
        chunks.append(text[start:end])
        if end == length:
            break
        start = end - CHUNK_OVERLAP  # overlap 적용

    return [c for c in chunks if c.strip()]


# ── 메타데이터 구성 ───────────────────────────────────────────────────────────

def build_metadata(page: dict) -> dict:
    """
    저장 메타데이터:
        page_id, title, url, parent_id, parent_title,
        depth, breadcrumb, space_key, author, last_modified,
        version, labels
    """
    ancestors = page.get("ancestors", [])
    version   = page.get("version", {})
    labels    = [
        lbl["name"]
        for lbl in page.get("metadata", {}).get("labels", {}).get("results", [])
    ]

    breadcrumb_parts = [a["title"] for a in ancestors] + [page["title"]]

    return {
        "page_id":       str(page["id"]),
        "title":         page["title"],
        "url":           f"{BASE_URL}{page['_links']['webui'] if page['_links']['webui'].startswith('/wiki') else '/wiki' + page['_links']['webui']}",
        "parent_id":     str(ancestors[-1]["id"]) if ancestors else "",
        "parent_title":  ancestors[-1]["title"]   if ancestors else "",
        "depth":         str(len(ancestors)),
        "breadcrumb":    " > ".join(breadcrumb_parts),
        "space_key":     SPACE_KEY,
        "author":        version.get("by", {}).get("displayName", ""),
        "last_modified": version.get("when", ""),
        "version":       str(version.get("number", 1)),
        "labels":        ",".join(labels),
    }


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print(" Confluence → ChromaDB 임베딩")
    print("=" * 50)

    # ChromaDB 초기화
    chroma  = chromadb.PersistentClient(path=VECTOR_DB_PATH)
    col     = chroma.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"\nChromaDB 컬렉션: '{COLLECTION_NAME}'  →  {VECTOR_DB_PATH}/")

    # 임베딩 모델 로드
    print(f"임베딩 모델 로드: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    # 전체 페이지 수집
    print(f"\nConfluence Space '{SPACE_KEY}' 페이지 수집 중...")
    pages = fetch_all_pages()
    print(f"총 {len(pages)}개 페이지 수집 완료\n")

    # 임베딩 & 저장
    total_chunks = 0
    skipped      = 0

    for i, page in enumerate(pages, 1):
        body_html = page.get("body", {}).get("storage", {}).get("value", "")
        text      = parse_html(body_html)

        if not text.strip():
            print(f"[{i:3}/{len(pages)}] 건너뜀 (내용 없음): {page['title']}")
            skipped += 1
            continue

        chunks   = chunk_text(text)
        metadata = build_metadata(page)

        # 임베딩: 제목 + 청크 (검색 품질 향상)
        # 저장:   청크만 (표시용 원본 유지)
        title        = page["title"]
        embed_texts  = [f"{title}\n{chunk}" for chunk in chunks]

        ids        = [f"{page['id']}_chunk_{j}" for j in range(len(chunks))]
        embeddings = model.encode(embed_texts).tolist()
        metadatas  = [{**metadata, "chunk_index": str(j)} for j in range(len(chunks))]

        # 이미 존재하는 청크 삭제 후 재삽입 (멱등성 보장)
        existing_ids = col.get(ids=ids)["ids"]
        if existing_ids:
            col.delete(ids=existing_ids)

        col.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

        total_chunks += len(chunks)
        print(f"[{i:3}/{len(pages)}] {page['title'][:45]:<45} → {len(chunks)}청크")

    # 결과 요약
    print(f"\n{'=' * 50}")
    print(f" 완료: {len(pages) - skipped}개 페이지 / {total_chunks}개 청크 저장")
    print(f" 건너뜀: {skipped}개 (내용 없음)")
    print(f"{'=' * 50}")
    print(f"\n[다른 프로젝트에서 사용하는 방법]")
    print(f"  import chromadb")
    print(f"  from sentence_transformers import SentenceTransformer")
    print(f"  model  = SentenceTransformer('{EMBEDDING_MODEL}')")
    print(f"  client = chromadb.PersistentClient(path='{VECTOR_DB_PATH}')")
    print(f"  col    = client.get_collection('{COLLECTION_NAME}')")
    print(f"  q_emb  = model.encode(['검색할 질문']).tolist()")
    print(f"  result = col.query(query_embeddings=q_emb, n_results=5)")
    print(f"  # result['documents'], result['metadatas'] 로 접근")


if __name__ == "__main__":
    main()
