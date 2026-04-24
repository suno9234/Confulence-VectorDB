"""
Confluence 페이지 업로드 스크립트
content/index.yaml의 트리 구조를 읽어 Confluence에 페이지를 생성/업데이트합니다.

사용법:
    python upload_content.py

.env 필수 항목:
    CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN,
    CONFLUENCE_SPACE_KEY, ROOT_PAGE_ID
"""

import os
import json
import yaml
import requests
import markdown as md_lib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_URL   = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
EMAIL      = os.environ["CONFLUENCE_EMAIL"]
TOKEN      = os.environ["CONFLUENCE_API_TOKEN"]
SPACE_KEY  = os.environ["CONFLUENCE_SPACE_KEY"]
ROOT_ID    = os.environ["ROOT_PAGE_ID"]

AUTH    = (EMAIL, TOKEN)
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
CONTENT_DIR = Path("content")


# ── Confluence API 헬퍼 ──────────────────────────────────────────────────────

def api_get(path, params=None):
    resp = requests.get(f"{BASE_URL}{path}", auth=AUTH, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()


def api_post(path, data):
    resp = requests.post(f"{BASE_URL}{path}", auth=AUTH, headers=HEADERS, json=data)
    if not resp.ok:
        print(f"  [ERROR] POST {path}: {resp.status_code} {resp.text[:300]}")
        resp.raise_for_status()
    return resp.json()


def api_put(path, data):
    resp = requests.put(f"{BASE_URL}{path}", auth=AUTH, headers=HEADERS, json=data)
    if not resp.ok:
        print(f"  [ERROR] PUT {path}: {resp.status_code} {resp.text[:300]}")
        resp.raise_for_status()
    return resp.json()


# ── Space ID 조회 ─────────────────────────────────────────────────────────────

def get_space_id():
    data = api_get("/wiki/api/v2/spaces", params={"keys": SPACE_KEY, "limit": 1})
    results = data.get("results", [])
    if not results:
        raise ValueError(f"Space '{SPACE_KEY}'를 찾을 수 없습니다.")
    return results[0]["id"]


# ── 페이지 검색 (제목 + space 기준) ───────────────────────────────────────────

def find_page(title, space_id):
    data = api_get("/wiki/api/v2/pages", params={
        "title":   title,
        "spaceId": space_id,
        "limit":   1,
    })
    results = data.get("results", [])
    return results[0] if results else None


# ── Markdown → Confluence Storage Format 변환 ─────────────────────────────────

def to_storage(md_text):
    # markdown 라이브러리로 HTML 변환 후 Confluence storage format으로 사용
    html = md_lib.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br"],
    )
    return html


# ── 페이지 생성 / 업데이트 ────────────────────────────────────────────────────

def create_page(title, body_html, parent_id, space_id):
    payload = {
        "spaceId":  space_id,
        "status":   "current",
        "title":    title,
        "parentId": str(parent_id),
        "body": {
            "representation": "storage",
            "value": body_html,
        },
    }
    return api_post("/wiki/api/v2/pages", payload)


def update_page(page_id, title, body_html, current_version):
    payload = {
        "status": "current",
        "title":  title,
        "version": {"number": current_version + 1},
        "body": {
            "representation": "storage",
            "value": body_html,
        },
    }
    return api_put(f"/wiki/api/v2/pages/{page_id}", payload)


# ── 트리 순회 업로드 ──────────────────────────────────────────────────────────

def process_pages(pages, parent_id, space_id, depth=0):
    indent = "  " * depth
    for page_cfg in pages:
        title     = page_cfg["title"]
        file_path = CONTENT_DIR / page_cfg["file"]

        if not file_path.exists():
            print(f"{indent}[SKIP] 파일 없음: {file_path}")
            continue

        md_text   = file_path.read_text(encoding="utf-8")
        body_html = to_storage(md_text)

        existing = find_page(title, space_id)
        if existing:
            page_id = existing["id"]
            version = existing["version"]["number"]
            update_page(page_id, title, body_html, version)
            print(f"{indent}[업데이트] {title}")
        else:
            result  = create_page(title, body_html, parent_id, space_id)
            page_id = result["id"]
            print(f"{indent}[생성] {title}")

        children = page_cfg.get("children", [])
        if children:
            process_pages(children, page_id, space_id, depth + 1)


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    index_path = CONTENT_DIR / "index.yaml"
    with open(index_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    print("Space ID 조회 중...")
    space_id = get_space_id()
    print(f"Space ID: {space_id}\n")

    print("페이지 업로드 시작\n" + "=" * 40)
    process_pages(config["pages"], ROOT_ID, space_id)
    print("\n" + "=" * 40)
    print("완료!")


if __name__ == "__main__":
    main()
