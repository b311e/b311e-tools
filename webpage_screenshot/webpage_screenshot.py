"""
Screenshot a list of webpages at 300 PPI and save to a project folder.

Prompts for:
  - Project name (becomes the output folder name)
  - Path to a .txt file containing URLs (one per line; blank lines and
    lines starting with '#' are ignored)

Each screenshot is a full-page PNG rendered at device_scale_factor 3.125
(= 300/96) and stamped with 300 DPI metadata. Filenames are
YYYY-MM-DD-page-title.png with the title slugified.
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path


def ensure_deps():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        from PIL import Image  # noqa: F401
        return
    except ImportError:
        pass

    print("Installing dependencies (no admin required)...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--user", "playwright", "pillow"]
    )
    subprocess.check_call(
        [sys.executable, "-m", "playwright", "install", "chromium"]
    )


def slugify(text: str, max_len: int = 80) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[\s_&]+", "-", text)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        text = "untitled"
    return text[:max_len].rstrip("-")


def prompt_project_name() -> str:
    while True:
        name = input("Project name: ").strip()
        if name:
            return name
        print("  Project name is required.")


def prompt_urls_file() -> Path:
    script_dir = Path(__file__).resolve().parent
    default = script_dir / "urls.txt"
    while True:
        prompt = f"Path to URLs .txt file [{default}]: "
        raw = input(prompt).strip().strip('"').strip("'")
        path = default if not raw else Path(raw).expanduser()
        if not path.is_absolute():
            path = script_dir / path
        if path.is_file():
            return path
        print(f"  File not found: {path}")


def load_urls(path: Path) -> list[str]:
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith(("http://", "https://")):
            line = "https://" + line
        urls.append(line)
    return urls


def unique_path(folder: Path, base: str, ext: str = ".png") -> Path:
    candidate = folder / f"{base}{ext}"
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = folder / f"{base}-{n}{ext}"
        if not candidate.exists():
            return candidate
        n += 1


def main():
    project = prompt_project_name()
    urls_path = prompt_urls_file()

    urls = load_urls(urls_path)
    if not urls:
        print("No URLs found in file.")
        sys.exit(1)

    out_dir = Path.cwd() / slugify(project)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    print(f"\nProject:  {project}")
    print(f"Output:   {out_dir}")
    print(f"URLs:     {len(urls)} from {urls_path}\n")

    ensure_deps()
    from playwright.sync_api import sync_playwright
    from PIL import Image

    scale = 300 / 96.0  # 3.125 — renders at 300 PPI relative to CSS pixels

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            device_scale_factor=scale,
        )
        page = context.new_page()

        for i, url in enumerate(urls, 1):
            print(f"  [{i}/{len(urls)}] {url}")
            try:
                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                except Exception:
                    # Fall back to whatever has loaded so far
                    pass

                title = ""
                try:
                    title = page.title() or ""
                except Exception:
                    pass
                if not title:
                    title = url.split("://", 1)[-1]

                base = f"{today}-{slugify(title)}"
                out_path = unique_path(out_dir, base)

                page.screenshot(path=str(out_path), full_page=True)

                # Stamp 300 DPI into PNG metadata
                with Image.open(out_path) as img:
                    img.save(out_path, dpi=(300, 300))

                print(f"      -> {out_path.name}")
            except Exception as e:
                print(f"      [error] {e}")

        browser.close()

    print(f"\nDone. Saved to: {out_dir}")


if __name__ == "__main__":
    main()
