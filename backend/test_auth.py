"""
Confluence API 인증 테스트 - Basic Auth vs Bearer
"""
import os, base64, requests
from dotenv import load_dotenv
load_dotenv()

BASE_URL = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
EMAIL    = os.environ["CONFLUENCE_EMAIL"]
TOKEN    = os.environ["CONFLUENCE_API_TOKEN"]
ROOT_ID  = os.environ["ROOT_PAGE_ID"]
URL      = f"{BASE_URL}/wiki/rest/api/content/{ROOT_ID}/child/page?limit=1"

basic = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()

for label, headers in [
    ("Basic Auth", {"Authorization": f"Basic {basic}",   "Accept": "application/json"}),
    ("Bearer",     {"Authorization": f"Bearer {TOKEN}",  "Accept": "application/json"}),
]:
    resp = requests.get(URL, headers=headers)
    print(f"{label}: {resp.status_code}", "✓" if resp.ok else f"→ {resp.text[:120]}")
