"""
Simple site crawler - finds all pages under a domain.
Usage: python crawl_site.py https://example.com
"""

import sys
import time
from collections import deque
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing dependencies (no admin required)...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "requests", "beautifulsoup4"])
    import requests
    from bs4 import BeautifulSoup


def crawl(start_url, delay=0.5, max_pages=500):
    parsed = urlparse(start_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    visited = set()
    queue = deque([start_url])
    found = []

    headers = {"User-Agent": "Mozilla/5.0 (compatible; site-crawler/1.0)"}

    print(f"Crawling: {base}\n")

    while queue and len(visited) < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if "text/html" not in resp.headers.get("Content-Type", ""):
                continue

            print(f"  [{len(visited):>4}] {url}")
            found.append(url)

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup.find_all("a", href=True):
                href = tag["href"].strip()
                full = urljoin(url, href)
                full = full.split("#")[0].split("?")[0]  # strip fragments/params
                if full.startswith(base) and full not in visited:
                    queue.append(full)

            time.sleep(delay)

        except Exception as e:
            print(f"  [skip] {url} — {e}")

    return found


if __name__ == "__main__":
    url = input("Enter URL to crawl: ").strip()
    if not url:
        print("No URL provided.")
        sys.exit(1)
    if not url.startswith("http"):
        url = "https://" + url

    delay = 0.5
    max_pages = 500

    pages = crawl(url, delay=delay, max_pages=max_pages)

    output_file = "pages.txt"
    with open(output_file, "w") as f:
        f.write("\n".join(sorted(pages)))

    print(f"\nDone. {len(pages)} pages found.")
    print(f"Results saved to: {output_file}")