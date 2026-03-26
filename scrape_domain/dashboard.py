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

DEFAULT_DOMAIN = "leg.state.co.us"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; url-dashboard/1.0)"}

def cache_file_for(domain):
    safe = re.sub(r"[^\w.-]", "_", domain)
    return f"url_cache_{safe}.json"

def cdx_url_for(domain):
    return (
        "http://web.archive.org/cdx/search/cdx"
        f"?url={domain}/*"
        "&output=text"
        "&fl=original"
        "&collapse=urlkey"
        "&limit=50000"
    )

st.set_page_config(page_title="Domain URL Inventory", layout="centered")

st.markdown("""
<style>
    /* Primary button — WCAG AA compliant (contrast ratio ~4.6:1) */
    button[kind="primary"] {
        background-color: #217645 !important;
        color: #ffffff !important;
        border: none !important;
    }
    button[kind="primary"]:hover {
        background-color: #1a5e37 !important;
    }
    button[kind="primary"]:focus-visible {
        outline: 3px solid #217645 !important;
        outline-offset: 2px !important;
    }
    /* Secondary buttons — ensure visible focus ring */
    button[kind="secondary"]:focus-visible {
        outline: 3px solid #1a5276 !important;
        outline-offset: 2px !important;
    }
    .metric-card {
        border-radius: 2px;
        padding: 1.2rem 1.5rem;
        border: 1px solid #e0ddd8;
    }
    /* Status badges — WCAG AA compliant contrast */
    .status-live { color: #1b5e1b; background: #e8f5e8; padding: 2px 8px; border-radius: 2px; font-size: 1em; font-weight: 600; }
    .status-dead { color: #7a1414; background: #fde8e8; padding: 2px 8px; border-radius: 2px; font-size: 1em; font-weight: 600; }
    .status-error { color: #4a3b00; background: #fff8e0; padding: 2px 8px; border-radius: 2px; font-size: 1em; font-weight: 600; }
    /* Section headings (h2) */
    h2 {
        font-size: 1.2rem !important;
        font-weight: 600 !important;
        color: inherit !important;
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }
    div[data-testid="stProgress"] > div { background-color: #1a4a7a; }
</style>
""", unsafe_allow_html=True)


# --- Cache helpers ---

def load_cache(cache_file):
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    return None

def save_cache(data, cache_file):
    with open(cache_file, "w") as f:
        json.dump(data, f)


# --- CDX fetch ---

def fetch_cdx(domain, progress_callback=None):
    for attempt in range(3):
        try:
            resp = requests.get(cdx_url_for(domain), headers=HEADERS, timeout=120, stream=True)
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


HTTP_STATUS_DESCRIPTIONS = {
    200: "OK",
    201: "Created",
    204: "No Content",
    301: "Moved Permanently",
    302: "Found (Temporary Redirect)",
    303: "See Other",
    304: "Not Modified",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    410: "Gone",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}

def status_label(code):
    if isinstance(code, int):
        desc = HTTP_STATUS_DESCRIPTIONS.get(code, "Unknown")
        return f"{code} {desc}"
    return str(code)


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

st.title("Domain URL Inventory")
st.caption("Wayback Machine CDX + live status checker")

domain = st.text_input("Domain to scan", value=DEFAULT_DOMAIN, placeholder="example.com")
cache_file = cache_file_for(domain)
cache = load_cache(cache_file)

col_info, col_run = st.columns([3, 1])
with col_info:
    if cache:
        st.info(f"Last run: **{cache.get('timestamp', 'unknown')}** — {len(cache.get('results', []))} URLs checked for **{cache.get('domain', domain)}**")
    else:
        st.warning(f"No cached data for **{domain}**. Click **Run Check** to fetch and test all URLs.")

with col_run:
    run_now = st.button("▶ Run Check", type="primary", use_container_width=True)
    test_now = st.button("Test (20 URLs)", use_container_width=True)
    if cache:
        clear = st.button("Clear Cache", use_container_width=True)
        if clear:
            os.remove(cache_file)
            st.rerun()

if run_now or test_now:
    st.write(f"Fetching URL list for **{domain}** from Wayback Machine CDX API...")
    fetch_status = st.empty()
    try:
        urls = fetch_cdx(domain, progress_callback=lambda n: fetch_status.text(f"Fetched {n:,} URLs so far..."))
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
        "domain": domain,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "results": results,
    }
    save_cache(cache, cache_file)
    st.success("✓ Done!")
    st.rerun()


if cache:
    df = pd.DataFrame(cache["results"])
    df["status_str"] = df["status"].astype(str)
    df["status_desc"] = df["status"].apply(status_label)
    df["live"] = df["status"] == 200

    live_df     = df[df["status"] == 200]
    redirect_df = df[df["status"].apply(lambda s: isinstance(s, int) and 300 <= s < 400)]
    error_df    = df[df["status_str"].str.startswith("ERROR")]
    dead_df     = df[~df.index.isin(live_df.index) & ~df.index.isin(redirect_df.index) & ~df.index.isin(error_df.index)]

    # --- Metrics ---
    st.markdown("---")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total URLs", len(df))
    m2.metric("Live (200)", len(live_df))
    m3.metric("Redirects (3xx)", len(redirect_df))
    m4.metric("Dead", len(dead_df))
    m5.metric("Errors", len(error_df))

    st.markdown("---")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["All URLs", "Live", "Redirects", "Dead", "Patterns"])

    with tab1:
        search = st.text_input("Filter URLs", placeholder="Type to filter...", key="all_search")
        filtered = df[df["url"].str.contains(search, case=False)] if search else df
        st.dataframe(
            filtered[["status_desc", "url", "path", "top"]].rename(columns={"status_desc": "Status", "url": "URL", "path": "Path", "top": "Top Segment"}),
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
        search3 = st.text_input("Filter redirects", placeholder="Type to filter...", key="redirect_search")
        filtered3 = redirect_df[redirect_df["url"].str.contains(search3, case=False)] if search3 else redirect_df
        st.dataframe(
            filtered3[["status_desc", "url", "path"]].rename(columns={"status_desc": "Status", "url": "URL", "path": "Path"}),
            use_container_width=True,
            height=500,
        )

    with tab4:
        search4 = st.text_input("Filter dead URLs", placeholder="Type to filter...", key="dead_search")
        filtered4 = dead_df[dead_df["url"].str.contains(search4, case=False)] if search4 else dead_df
        st.dataframe(
            filtered4[["status_desc", "url", "path"]].rename(columns={"status_desc": "Status", "url": "URL", "path": "Path"}),
            use_container_width=True,
            height=500,
        )

    with tab5:
        p1, p2, p3 = st.columns(3)

        with p1:
            st.header("Top-level segments")
            top_counts = live_df["top"].value_counts().reset_index()
            top_counts.columns = ["Segment", "Live URLs"]
            st.dataframe(top_counts, use_container_width=True, height=400)

        with p2:
            st.header("Second-level paths")
            second_counts = live_df["second"].value_counts().head(40).reset_index()
            second_counts.columns = ["Path", "Live URLs"]
            st.dataframe(second_counts, use_container_width=True, height=400)

        with p3:
            st.header("File extensions")
            ext_counts = live_df["ext"].value_counts().reset_index()
            ext_counts.columns = ["Extension", "Count"]
            st.dataframe(ext_counts, use_container_width=True, height=400)

    # --- Export ---
    st.markdown("---")
    st.header("Export")
    csv = df[["status_desc", "url", "path", "top", "second", "ext"]].rename(columns={"status_desc": "status"}).to_csv(index=False)
    st.download_button("⬇ Download CSV", csv, "url_inventory.csv", "text/csv")