# Confluence Vector DB Embedder

Confluence 페이지를 트리 구조로 관리하고 벡터 DB로 임베딩하는 프로그램.

## 목적

1. Confluence에 트리 구조 페이지를 생성/업데이트
2. Confluence 페이지를 읽어 메타데이터와 함께 벡터 DB에 저장
3. 벡터 DB는 다른 시스템에서 재사용 가능하도록 독립 구성

---

## 프로젝트 구조

```
.
├── .env                  # API 토큰, URL 등 시크릿
├── .env.example          # .env 템플릿 (커밋용)
├── CLAUDE.md
├── requirements.txt
├── content/              # 업로드할 페이지 원본 (Markdown)
│   ├── index.yaml        # 페이지 트리 구조 정의
│   └── pages/
│       └── *.md
├── upload_content.py     # Confluence에 페이지 업로드
├── embed_pages.py        # 페이지 읽어서 벡터 DB 생성
└── vector_db/            # 생성된 ChromaDB 파일 (gitignore)
```

---

## 환경 변수 (.env)

```env
CONFLUENCE_BASE_URL=https://your-domain.atlassian.net
CONFLUENCE_EMAIL=your@email.com
CONFLUENCE_API_TOKEN=your_api_token
CONFLUENCE_SPACE_KEY=YOUR_SPACE

EMBEDDING_MODEL=all-MiniLM-L6-v2   # sentence-transformers 모델
VECTOR_DB_PATH=./vector_db          # ChromaDB 저장 경로
VECTOR_DB_COLLECTION=confluence     # 컬렉션 이름
```

---

## 모듈 설계

### 1. `upload_content.py` — 콘텐츠 업로드

- `content/index.yaml`에서 페이지 트리 구조를 읽음
- 부모-자식 관계를 유지하며 Confluence에 페이지 생성/업데이트
- Markdown → Confluence Storage Format 변환 (md2cf 또는 직접 파싱)

**index.yaml 예시:**
```yaml
root_page_id: "123456"   # Confluence 루트 페이지 ID
pages:
  - title: "개요"
    file: pages/overview.md
    children:
      - title: "설치 방법"
        file: pages/install.md
      - title: "API 레퍼런스"
        file: pages/api.md
        children:
          - title: "인증"
            file: pages/api_auth.md
```

### 2. `embed_pages.py` — 벡터 DB 생성

- Confluence REST API로 Space 내 모든 페이지 재귀 수집
- 각 페이지를 청크 분할 후 임베딩
- ChromaDB에 메타데이터와 함께 저장

**저장되는 메타데이터:**
```python
{
    "page_id": str,          # Confluence 페이지 ID
    "title": str,            # 페이지 제목
    "url": str,              # 페이지 URL
    "parent_id": str,        # 부모 페이지 ID (트리 구조)
    "parent_title": str,     # 부모 페이지 제목
    "depth": int,            # 트리 깊이 (루트=0)
    "breadcrumb": str,       # "루트 > 상위 > 현재" 경로
    "space_key": str,        # Confluence Space
    "author": str,           # 최초 작성자
    "last_modified": str,    # 최종 수정일 (ISO8601)
    "version": int,          # 페이지 버전 번호
    "labels": list[str],     # Confluence 레이블/태그
    "chunk_index": int,      # 청크 번호 (긴 페이지 분할 시)
}
```

---

## 기술 스택

| 역할 | 라이브러리 |
|------|-----------|
| Confluence API | `requests` (REST API v2 직접 호출) |
| 환경 변수 | `python-dotenv` |
| 임베딩 | `sentence-transformers` |
| 벡터 DB | `chromadb` (로컬 파일 기반, 이식성 높음) |
| Markdown 변환 | `md2cf` 또는 `mistune` |
| HTML 파싱 | `beautifulsoup4` |

ChromaDB를 선택한 이유: 별도 서버 없이 로컬 파일(`./vector_db/`)로 저장되어
다른 프로젝트에서 경로만 지정하면 바로 로드 가능.

---

## 구현 순서

1. `.env` + `requirements.txt` 작성
2. `upload_content.py` — Confluence API 연결 및 트리 구조 페이지 생성
3. `embed_pages.py` — 페이지 수집 → 청크 분할 → 임베딩 → ChromaDB 저장
4. 동작 확인 및 README 작성

---

## Confluence API 엔드포인트

```
# 페이지 목록 (Space 기준)
GET /wiki/api/v2/spaces/{spaceId}/pages

# 자식 페이지
GET /wiki/api/v2/pages/{pageId}/children

# 페이지 생성
POST /wiki/api/v2/pages

# 페이지 수정
PUT /wiki/api/v2/pages/{pageId}

# 페이지 라벨
GET /wiki/rest/api/content/{pageId}/label
```

인증: Basic Auth (`email:api_token` → Base64)
