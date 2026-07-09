"""
NetApp Active IQ Advisor - Desktop Launcher
===========================================
Starts the built-in CORS proxy server in a background thread, then opens
the dashboard in a native OS webview (WebView2 on Windows, WKWebView on macOS).

No external browser required. No CORS restrictions. No Python installation
required on end-user machines when distributed as a PyInstaller bundle.

Run directly:  python launcher.py
Build Windows: build_windows.bat
Build macOS:   ./build_mac.sh
"""

import sys
import os
import threading
import time
import socket
import json
import subprocess
import http.server
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Path resolution: works both as a plain script and as a PyInstaller bundle.
# When frozen by PyInstaller, all bundled data files live in sys._MEIPASS.
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

APP_NAME = "NetApp Active IQ Advisor"
APP_PORT = 8080


# ---------------------------------------------------------------------------
# Embedded CORS Proxy Server (identical logic to server.py, self-contained)
# ---------------------------------------------------------------------------

class _SuppressLogs(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silent in production


class AIQProxyHandler(_SuppressLogs):
    """
    Serves static assets from BASE_DIR and transparently proxies /api/* calls
    to api.activeiq.netapp.com, injecting CORS headers on every response.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma",  "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200, "OK")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._proxy("GET")
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/app/update":
            self._handle_git_update()
        elif self.path.startswith("/api/") or self.path == "/graphql":
            self._proxy("POST")
        else:
            self.send_error(404, "Not Found")

    def _handle_git_update(self):
        try:
            result = subprocess.run(
                ["git", "pull"], capture_output=True, text=True,
                timeout=30, cwd=BASE_DIR
            )
            ok = result.returncode == 0
            payload = {
                "status":  "success" if ok else "error",
                "message": "Updated successfully!" if ok
                           else (result.stderr or result.stdout or "git pull failed")
            }
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": str(exc)}).encode())

    def _proxy(self, method):
        if self.path == "/graphql":
            target = "https://api.activeiq.netapp.com/graphql"
        else:
            target = "https://api.activeiq.netapp.com/v1" + self.path[4:]

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length > 0 else None
        headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ("host", "connection", "content-length", "accept-encoding")
        }
        if method == "POST" and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(target, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                data = resp.read()
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() not in ("transfer-encoding", "content-encoding",
                                         "access-control-allow-origin"):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as exc:
            data = exc.read()
            self.send_response(exc.code)
            for k, v in exc.headers.items():
                if k.lower() not in ("transfer-encoding", "content-encoding",
                                     "access-control-allow-origin"):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(exc).encode())


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

def _find_free_port(preferred=APP_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port):
    server = http.server.HTTPServer(("127.0.0.1", port), AIQProxyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="aiq-proxy")
    thread.start()
    return server


def _wait_for_server(port, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    port   = _find_free_port(APP_PORT)
    server = _start_server(port)

    if not _wait_for_server(port):
        sys.exit(f"ERROR: Local server failed to start on port {port}.")

    url = f"http://127.0.0.1:{port}/index.html"

    try:
        import webview

        webview.create_window(
            title       = APP_NAME,
            url         = url,
            width       = 1600,
            height      = 960,
            min_size    = (1200, 720),
            resizable   = True,
            text_select = True,
            zoomable    = True,
        )
        webview.start(debug=False)

    except ImportError:
        # Development fallback: open in browser if pywebview is not installed
        import webbrowser
        print(f"\n[AIQ Advisor] pywebview not found. Opening browser: {url}")
        print("Install with:  pip install pywebview\n")
        webbrowser.open(url)
        try:
            input("Press Enter to stop the server...\n")
        except (KeyboardInterrupt, EOFError):
            pass

    finally:
        server.shutdown()


if __name__ == "__main__":
    main()