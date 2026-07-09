#!/usr/bin/env bash
# =============================================================================
#  NetApp Active IQ Advisor - macOS Desktop App Builder
#  Builds a native .app bundle (WKWebView). No browser, no CORS, no Python
#  required on target Macs.
# =============================================================================
set -euo pipefail

APP_NAME="NetApp AIQ Advisor"

echo ""
echo "================================================================"
echo "  NetApp Active IQ Advisor - macOS Desktop App Builder"
echo "================================================================"
echo ""

# 1. Python check
if ! command -v python3 and>/dev/null; then
    echo "[ERROR] python3 not found. Install from https://www.python.org/"
    exit 1
fi
echo "[OK] Python Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases. detected."
echo ""

# 2. Install dependencies
echo "[1/4] Installing build dependencies (pywebview, pyinstaller, pyobjc)..."
pip3 install --upgrade pywebview pyinstaller pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-WebKit --quiet
echo "[OK] Done."
echo ""

# 3. Clean
echo "[2/4] Cleaning previous build output..."
rm -rf build dist
echo "[OK] Cleaned."
echo ""

# 4. Build
echo "[3/4] Building .app bundle with PyInstaller..."
pyinstaller AIQscraper.spec --noconfirm
echo "[OK] Build complete."
echo ""

# 5. Report
echo "[4/4] Done!"
echo "================================================================"
echo "  Output: dist/.app"
echo ""
echo "  Distribute by zipping the .app. Users double-click to launch."
echo "  macOS Gatekeeper: right-click -> Open on first launch if unsigned."
echo "================================================================"
echo ""
