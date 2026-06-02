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

import base64 as _b64
_BASIC = _b64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
HEADERS = {
    "Content-Type":  "application/json",
    "Accept":        "application/json",
    "Authorization": f"Basic {_BASIC}",
}
CONTENT_DIR = Path("content")


# ── Confluence API 헬퍼 ──────────────────────────────────────────────────────

def api_get(path, params=None):
    resp = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()


def api_post(path, data):
    resp = requests.post(f"{BASE_URL}{path}", headers=HEADERS, json=data)
    if not resp.ok:
        print(f"  [ERROR] POST {path}: {resp.status_code} {resp.text[:300]}")
        resp.raise_for_status()
    return resp.json()


def api_put(path, data):
    resp = requests.put(f"{BASE_URL}{path}", headers=HEADERS, json=data)
    if not resp.ok:
        print(f"  [ERROR] PUT {path}: {resp.status_code} {resp.text[:300]}")
        resp.raise_for_status()
    return resp.json()


# ── 페이지 검색 (부모 자식 목록에서 탐색) ────────────────────────────────────

def find_page(title, parent_id):
    """부모 페이지의 자식 중 title이 일치하는 페이지를 반환."""
    start = 0
    while True:
        data = api_get(
            f"/wiki/rest/api/content/{parent_id}/child/page",
            params={"limit": 50, "start": start, "expand": "version"},
        )
        for page in data.get("results", []):
            if page["title"] == title:
                return page
        if not data.get("_links", {}).get("next"):
            return None
        start += 50


# ── Markdown → Confluence Storage Format 변환 ─────────────────────────────────

def to_storage(md_text):
    # markdown 라이브러리로 HTML 변환 후 Confluence storage format으로 사용
    html = md_lib.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br"],
    )
    return html


# ── 페이지 생성 / 업데이트 ────────────────────────────────────────────────────

def create_page(title, body_html, parent_id):
    payload = {
        "type":      "page",
        "title":     title,
        "space":     {"key": SPACE_KEY},
        "ancestors": [{"id": str(parent_id)}],
        "body": {
            "storage": {
                "value":          body_html,
                "representation": "storage",
            }
        },
    }
    return api_post("/wiki/rest/api/content", payload)


def update_page(page_id, title, body_html, current_version):
    payload = {
        "type":    "page",
        "title":   title,
        "version": {"number": current_version + 1},
        "body": {
            "storage": {
                "value":          body_html,
                "representation": "storage",
            }
        },
    }
    return api_put(f"/wiki/rest/api/content/{page_id}", payload)


# ── 트리 순회 업로드 ──────────────────────────────────────────────────────────

def process_pages(pages, parent_id, depth=0):
    indent = "  " * depth
    for page_cfg in pages:
        title     = page_cfg["title"]
        file_path = CONTENT_DIR / page_cfg["file"]

        if not file_path.exists():
            print(f"{indent}[SKIP] 파일 없음: {file_path}")
            continue

        raw       = file_path.read_text(encoding="utf-8")
        body_html = raw if file_path.suffix == ".xml" else to_storage(raw)

        existing = find_page(title, parent_id)
        if existing:
            page_id = existing["id"]
            version = existing["version"]["number"]
            update_page(page_id, title, body_html, version)
            print(f"{indent}[업데이트] {title}")
        else:
            result  = create_page(title, body_html, parent_id)
            page_id = result["id"]
            print(f"{indent}[생성] {title}")

        children = page_cfg.get("children", [])
        if children:
            process_pages(children, page_id, depth + 1)


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    index_path = CONTENT_DIR / "index.yaml"
    with open(index_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    print("페이지 업로드 시작\n" + "=" * 40)
    process_pages(config["pages"], ROOT_ID)
    print("\n" + "=" * 40)
    print("완료!")


if __name__ == "__main__":
    main()
