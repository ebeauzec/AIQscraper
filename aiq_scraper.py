"""
NetApp Active IQ Portal Scraper v2
===================================
Opens a real browser, you log in ONCE (session saved for future runs),
then captures all API traffic the portal generates.

Usage:
  python aiq_scraper.py                              # Uses saved session
  python aiq_scraper.py --fresh                      # Fresh login (clears saved session)
  python aiq_scraper.py -s "Vodacom South Africa"    # Custom search terms
"""

import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
except ImportError:
    print("ERROR: pip install playwright && playwright install chromium")
    sys.exit(1)

# -- Config ------------------------------------------------------------------
SCRIPT_DIR      = Path(__file__).parent
OUTPUT_FILE     = SCRIPT_DIR / "aiq_scraped_data.json"
ENDPOINTS_FILE  = SCRIPT_DIR / "aiq_scraped_endpoints.json"
PROFILE_DIR     = SCRIPT_DIR / ".aiq_browser_profile"
AIQ_URL         = "https://activeiq.netapp.com"

DEFAULT_SEARCHES = ["Vodacom South Africa", "Telkom SA", "Liberty Group"]
SEED_SERIALS     = ["211839000195", "952239002356", "952239002659",
                    "952239002236", "952239002406"]


class AIQScraper:
    def __init__(self, searches=None):
        self.searches  = searches or DEFAULT_SEARCHES
        self.responses = []     # every captured API response
        self.systems   = []     # extracted system-like records

    # -- Network interception ------------------------------------------------
    def _on_response(self, response):
        url = response.url
        if not any(d in url for d in ["activeiq.netapp.com", "cloud.netapp.com",
                                       "aiq-api", "netapp"]):
            return
        if any(e in url for e in [".js", ".css", ".png", ".jpg", ".svg",
                                   ".woff", ".ico", ".map"]):
            return
        try:
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                try:
                    body = response.json()
                except Exception:
                    return
            else:
                body = response.json()

            rec = {
                "url": url, "status": response.status,
                "method": response.request.method,
                "ts": datetime.now().isoformat(),
                "body": body,
                "size": len(json.dumps(body, default=str)),
            }
            self.responses.append(rec)

            body_s = json.dumps(body, default=str)
            empty  = body_s in ["{}", "[]", "null", '""']
            tag    = "  EMPTY " if empty else f"  DATA  "
            sz     = f"({len(body_s):,} bytes)" if not empty else ""
            status = response.status
            print(f"  [{status}] {tag} {sz:>16}  {response.request.method:4}  {url[:130]}")

            if not empty:
                self._extract_systems(body, url)

        except Exception:
            pass

    def _extract_systems(self, data, src):
        """Pull system-like records out of any response shape."""
        recs = []
        if isinstance(data, list):
            recs = data
        elif isinstance(data, dict):
            for k in ["results","hits","data","items","records",
                      "systemDetailsByInventory","systemList","systems",
                      "watchListData","watchlists","customers","aggregates",
                      "clusterDetails","inventoryList","searchResults",
                      "nodeList","nodes","response"]:
                v = data.get(k)
                if isinstance(v, list) and len(v) > 0:
                    recs = v
                    break
            if not recs:
                for v in data.values():
                    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                        if any(f in v[0] for f in ["serialNumber","serial_number",
                                                    "systemName","hostName","model"]):
                            recs = v
                            break

        for r in recs:
            if isinstance(r, dict) and any(f in r for f in
                    ["serialNumber","serial_number","systemSerialNumber",
                     "systemName","hostName","clusterName"]):
                r["_src"] = src
                self.systems.append(r)

    # -- Main flow -----------------------------------------------------------
    def run(self, fresh=False):
        print("=" * 72)
        print("  NetApp Active IQ Portal Scraper")
        print("  Searches: " + ", ".join(self.searches))
        print("=" * 72)

        if fresh and PROFILE_DIR.exists():
            import shutil
            shutil.rmtree(PROFILE_DIR, ignore_errors=True)
            print("  (Cleared saved browser profile)")

        with sync_playwright() as p:
            # Persistent context = cookies/session survive between runs
            ctx = p.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                headless=False,
                viewport={"width": 1440, "height": 900},
                args=["--start-maximized"],
                ignore_default_args=["--enable-automation"],
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            # Start capturing BEFORE navigation
            page.on("response", self._on_response)

            print(f"\n-> Opening {AIQ_URL} ...")
            page.goto(AIQ_URL, wait_until="domcontentloaded", timeout=60000)

            # Wait a few seconds to see if session is still valid
            time.sleep(5)

            # Check if already logged in by looking for authenticated API calls
            authed = any(
                r["status"] == 200 and "user" in r["url"]
                for r in self.responses
            )

            if authed:
                print("\n  Session restored from previous login!")
            else:
                print("\n" + "=" * 72)
                print("  LOG IN to Active IQ in the browser window.")
                print("  Take your time -- complete the full SSO flow.")
                print("  When you see the AIQ dashboard, come back here.")
                print("=" * 72)
                input("\n  >>> Press ENTER here when you are logged in... ")
                print("  Continuing...")

            # Give dashboard time to load its initial API calls
            print("\n-> Waiting for dashboard data to load...")
            time.sleep(5)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PwTimeout:
                pass

            print(f"\n  Dashboard: {len(self.responses)} API responses captured")
            print(f"             {len(self.systems)} system records extracted")

            # -- Navigate key pages ------------------------------------------
            print("\n-- Navigating key pages ------------------------------------------")
            for label, url in [
                ("Dashboard",  f"{AIQ_URL}/#/dashboard"),
                ("Watchlists", f"{AIQ_URL}/#/watchlist"),
            ]:
                print(f"\n  -> {label}: {url}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    time.sleep(4)
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception as e:
                    print(f"     Error: {e}")

            print(f"\n  After pages: {len(self.systems)} system records")

            # -- Search for customers ----------------------------------------
            print("\n-- Searching for customers ---------------------------------------")
            for term in self.searches:
                print(f"\n  Searching: \"{term}\"")
                self._do_search(page, term)
                print(f"    -> Total systems so far: {len(self.systems)}")

            # -- Search by serial --------------------------------------------
            print("\n-- Searching by serial numbers ------------------------------------")
            for sn in SEED_SERIALS[:2]:
                print(f"  Serial: {sn}")
                self._do_search(page, sn)

            # -- Save --------------------------------------------------------
            result = self._save()

            if result["total_systems"] == 0:
                print("\n" + "=" * 72)
                print("  No systems extracted automatically.")
                print("  The browser is still open. Try manually:")
                print("    1. Search for a customer name in the AIQ search bar")
                print("    2. Click on a system to load its details")
                print("    3. Navigate to Watchlist or Inventory pages")
                print("  All API traffic is still being captured.")
                print("  Press ENTER when done to save and close.")
                print("=" * 72)
                try:
                    input("\n  >>> Press ENTER to save and close... ")
                except (EOFError, KeyboardInterrupt):
                    pass
                self._save()

            ctx.close()
        print("\nDone.")

    def _do_search(self, page, term):
        """Try the portal's search functionality."""
        # Method 1: Use the global search bar
        selectors = [
            "input[type='search']",
            "input[placeholder*='earch']",
            "input[aria-label*='earch']",
            "[data-testid*='search'] input",
            "#globalSearch", "#searchInput",
            ".global-search input",
            "input.search-input",
        ]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    el.fill("")
                    time.sleep(0.3)
                    el.fill(term)
                    time.sleep(0.5)
                    el.press("Enter")
                    time.sleep(3)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except PwTimeout:
                        pass
                    print(f"    Searched via: {sel}")
                    return
            except Exception:
                continue

        # Method 2: Navigate to search URL
        try:
            enc = term.replace(" ", "%20")
            url = f"{AIQ_URL}/#/search?query={enc}"
            print(f"    No search input found, trying URL: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(4)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PwTimeout:
                pass
        except Exception as e:
            print(f"    Search error: {e}")

    def _save(self):
        # Deduplicate by serial
        seen = set()
        unique = []
        for s in self.systems:
            sn = str(s.get("serialNumber") or s.get("serial_number") or
                     s.get("systemSerialNumber") or "").strip()
            if sn and sn not in seen:
                seen.add(sn)
                unique.append(s)

        result = {
            "scrape_timestamp": datetime.now().isoformat(),
            "searches": self.searches,
            "total_api_responses": len(self.responses),
            "total_systems": len(unique),
            "systems": unique,
        }
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)

        # Endpoint log
        eps = []
        for r in self.responses:
            b = json.dumps(r.get("body", {}), default=str)
            body_obj = r.get("body", {})
            eps.append({
                "url": r["url"], "method": r["method"], "status": r["status"],
                "size": len(b), "empty": b in ["{}", "[]", "null", '""'],
                "keys": list(body_obj.keys()) if isinstance(body_obj, dict) else type(body_obj).__name__,
                "preview": b[:500],
            })
        with open(ENDPOINTS_FILE, "w", encoding="utf-8") as f:
            json.dump(eps, f, indent=2, default=str)

        print(f"\n  Saved: {OUTPUT_FILE.name}")
        print(f"    {len(unique)} unique systems")
        print(f"    {len(eps)} API responses logged -> {ENDPOINTS_FILE.name}")
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", "-s", action="append",
                        help="Customer name to search (repeatable)")
    parser.add_argument("--fresh", action="store_true",
                        help="Clear saved session and log in fresh")
    args = parser.parse_args()

    scraper = AIQScraper(searches=args.search or DEFAULT_SEARCHES)
    scraper.run(fresh=args.fresh)
