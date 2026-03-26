"""
CLICS URL Inventory Dashboard
Run with: streamlit run dashboard.py
"""

import time
import re
import json
import os
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse

try:
    import streamlit as st
    import requests
    import pandas as pd
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "streamlit", "requests", "pandas"])
    import streamlit as st
    import requests
    import pandas as pd

CACHE_FILE = "url_cache.json"
CDX_URL = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=leg.state.co.us/*"
    "&output=text"
    "&fl=original"
    "&collapse=urlkey"
    "&limit=50000"
)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; leg-state-co-us-dashboard/1.0)"}

st.set_page_config(page_title="leg.state.co.us Inventory", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #f8f7f4; }
    .metric-card {
        background: white;
        border-radius: 2px;
        padding: 1.2rem 1.5rem;
        border: 1px solid #e0ddd8;
    }
    .status-live { color: #2d6a2d; background: #e8f5e8; padding: 2px 8px; border-radius: 2px; font-size: 0.85em; font-weight: 600; }
    .status-dead { color: #8b1a1a; background: #fde8e8; padding: 2px 8px; border-radius: 2px; font-size: 0.85em; font-weight: 600; }
    .status-error { color: #5c4a00; background: #fff8e0; padding: 2px 8px; border-radius: 2px; font-size: 0.85em; font-weight: 600; }
    div[data-testid="stProgress"] > div { background-color: #1a4a7a; }
</style>
""", unsafe_allow_html=True)


# --- Cache helpers ---

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return None

def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)


# --- CDX fetch ---

def fetch_cdx(progress_callback=None):
    for attempt in range(3):
        try:
            resp = requests.get(CDX_URL, headers=HEADERS, timeout=120, stream=True)
            resp.raise_for_status()
            lines = []
            for line in resp.iter_lines():
                if line:
                    lines.append(line.decode("utf-8").strip())
                    if progress_callback and len(lines) % 500 == 0:
                        progress_callback(len(lines))
            return lines
        except Exception as e:
            if attempt < 2:
                time.sleep(5)
            else:
                raise e


# --- URL checking ---

def check_url(url):
    try:
        r = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
        return r.status_code
    except requests.exceptions.SSLError:
        try:
            r = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True, verify=False)
            return r.status_code
        except Exception as e:
            return f"ERROR: {e}"
    except Exception as e:
        return f"ERROR: {e}"


def relative_path(url):
    return urlparse(url).path.rstrip("/") or "/"

def top_segment(path):
    parts = path.strip("/").split("/")
    return f"/{parts[0]}" if parts and parts[0] else "/"

def second_segment(path):
    parts = path.strip("/").split("/")
    return f"/{parts[0]}/{parts[1]}" if len(parts) >= 2 and parts[1] else top_segment(path)

def file_ext(path):
    m = re.search(r"\.(\w+)$", path)
    return m.group(1) if m else "(none)"


# --- Main app ---

st.title("🏛️ CLICS URL Inventory")
st.caption("leg.state.co.us — Wayback Machine CDX + live status checker")

cache = load_cache()

col_info, col_run = st.columns([3, 1])
with col_info:
    if cache:
        st.info(f"Last run: **{cache.get('timestamp', 'unknown')}** — {len(cache.get('results', []))} URLs checked")
    else:
        st.warning("No cached data yet. Click **Run Check** to fetch and test all URLs.")

with col_run:
    run_now = st.button("▶ Run Check", type="primary", use_container_width=True)
    test_now = st.button("🧪 Test (20 URLs)", use_container_width=True)
    if cache:
        clear = st.button("🗑 Clear Cache", use_container_width=True)
        if clear:
            os.remove(CACHE_FILE)
            st.rerun()

if run_now or test_now:
    st.write("Fetching URL list from Wayback Machine CDX API...")
    fetch_status = st.empty()
    try:
        urls = fetch_cdx(progress_callback=lambda n: fetch_status.text(f"Fetched {n:,} URLs so far..."))
    except Exception as e:
        st.error(f"CDX fetch failed: {e}")
        st.stop()
    fetch_status.empty()
    if test_now:
        urls = urls[:20]
    st.write(f"✓ {len(urls):,} URLs retrieved. Checking live status...")

    results = []
    progress = st.progress(0, text="Checking URLs...")
    total = len(urls)
    for i, url in enumerate(urls):
        code = check_url(url)
        path = relative_path(url)
        results.append({
            "url": url,
            "status": code,
            "path": path,
            "top": top_segment(path),
            "second": second_segment(path),
            "ext": file_ext(path),
        })
        pct = (i + 1) / total
        progress.progress(pct, text=f"Checking URLs: {i + 1:,} / {total:,} ({pct:.0%})")
        time.sleep(0.3)
    progress.empty()

    cache = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "results": results,
    }
    save_cache(cache)
    st.success("✓ Done!")
    st.rerun()


if cache:
    df = pd.DataFrame(cache["results"])
    df["status_str"] = df["status"].astype(str)
    df["live"] = df["status"] == 200

    live_df  = df[df["status"] == 200]
    dead_df  = df[df["status"] != 200]
    error_df = df[df["status_str"].str.startswith("ERROR")]

    # --- Metrics ---
    st.markdown("---")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total URLs", len(df))
    m2.metric("Live (200)", len(live_df))
    m3.metric("Dead / Redirect", len(dead_df) - len(error_df))
    m4.metric("Errors", len(error_df))

    st.markdown("---")
    tab1, tab2, tab3, tab4 = st.tabs(["📋 All URLs", "✅ Live", "❌ Dead / Other", "📊 Patterns"])

    with tab1:
        search = st.text_input("Filter URLs", placeholder="Type to filter...", key="all_search")
        filtered = df[df["url"].str.contains(search, case=False)] if search else df
        st.dataframe(
            filtered[["status", "url", "path", "top"]].rename(columns={"status": "Status", "url": "URL", "path": "Path", "top": "Top Segment"}),
            use_container_width=True,
            height=500,
        )

    with tab2:
        search2 = st.text_input("Filter live URLs", placeholder="Type to filter...", key="live_search")
        filtered2 = live_df[live_df["url"].str.contains(search2, case=False)] if search2 else live_df
        st.dataframe(
            filtered2[["url", "path", "top", "second"]].rename(columns={"url": "URL", "path": "Path", "top": "Top Segment", "second": "Second Segment"}),
            use_container_width=True,
            height=500,
        )

    with tab3:
        search3 = st.text_input("Filter dead URLs", placeholder="Type to filter...", key="dead_search")
        filtered3 = dead_df[dead_df["url"].str.contains(search3, case=False)] if search3 else dead_df
        st.dataframe(
            filtered3[["status", "url", "path"]].rename(columns={"status": "Status", "url": "URL", "path": "Path"}),
            use_container_width=True,
            height=500,
        )

    with tab4:
        p1, p2, p3 = st.columns(3)

        with p1:
            st.subheader("Top-level segments")
            top_counts = live_df["top"].value_counts().reset_index()
            top_counts.columns = ["Segment", "Live URLs"]
            st.dataframe(top_counts, use_container_width=True, height=400)

        with p2:
            st.subheader("Second-level paths")
            second_counts = live_df["second"].value_counts().head(40).reset_index()
            second_counts.columns = ["Path", "Live URLs"]
            st.dataframe(second_counts, use_container_width=True, height=400)

        with p3:
            st.subheader("File extensions")
            ext_counts = live_df["ext"].value_counts().reset_index()
            ext_counts.columns = ["Extension", "Count"]
            st.dataframe(ext_counts, use_container_width=True, height=400)

    # --- Export ---
    st.markdown("---")
    st.subheader("Export")
    csv = df[["status", "url", "path", "top", "second", "ext"]].to_csv(index=False)
    st.download_button("⬇ Download CSV", csv, "url_inventory.csv", "text/csv")