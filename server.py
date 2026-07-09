import http.server
import urllib.request
import urllib.error
import sys

PORT = 8080

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Inject CORS headers for local origin access
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_OPTIONS(self):
        # Handle CORS preflight options check
        self.send_response(200, "OK")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/api/'):
            self.handle_proxy('GET')
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/api/app/update':
            self.handle_app_update()
        elif self.path.startswith('/api/') or self.path == '/graphql':
            self.handle_proxy('POST')
        else:
            self.send_error(404, "Not Found")

    def handle_app_update(self):
        import subprocess
        import json
        try:
            res = subprocess.run(["git", "pull"], capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                res_json = {"status": "success", "message": "Application code updated from Git repository successfully!"}
                self.wfile.write(json.dumps(res_json).encode('utf-8'))
            else:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                err_msg = res.stderr or res.stdout or "Git pull command failed."
                res_json = {"status": "error", "message": f"Git update failed: {err_msg.strip()}"}
                self.wfile.write(json.dumps(res_json).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            res_json = {"status": "error", "message": f"Server error: {str(e)}"}
            self.wfile.write(json.dumps(res_json).encode('utf-8'))

    def handle_proxy(self, method):
        if self.path == '/graphql':
            target_url = "https://api.activeiq.netapp.com/graphql"
        else:
            # Strip /api prefix, leaving e.g. /watchlist/all or /v2/watchlist/action
            endpoint = self.path[4:]  # removes leading /api

            # If the endpoint already carries an explicit version (/v2/...), use it
            # as-is on the base domain. Otherwise, default to /v1.
            import re
            if re.match(r'^/v\d+/', endpoint):
                target_url = f"https://api.activeiq.netapp.com{endpoint}"
            else:
                target_url = f"https://api.activeiq.netapp.com/v1{endpoint}"
        
        # Read request body data for POST
        content_length = int(self.headers.get('Content-Length', 0))
        req_data = self.rfile.read(content_length) if content_length > 0 else None
        
        # Clone headers (skipping host and connection to prevent conflicts)
        headers = {}
        for key, val in self.headers.items():
            if key.lower() not in ['host', 'connection', 'content-length', 'accept-encoding']:
                headers[key] = val

        if method == 'POST' and 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

        # Query NetApp API using standard urllib
        print(f"  → PROXY {method} {target_url}", flush=True)
        req = urllib.request.Request(target_url, data=req_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as response:
                res_data = response.read()
                print(f"  ← {response.status} ({len(res_data)} bytes)", flush=True)
                self.send_response(response.status)
                
                # Forward remote response headers
                for key, val in response.getheaders():
                    if key.lower() not in ['transfer-encoding', 'content-encoding', 'access-control-allow-origin']:
                        self.send_header(key, val)
                
                self.end_headers()
                self.wfile.write(res_data)
        except urllib.error.HTTPError as e:
            res_data = e.read()
            body_preview = res_data[:200].decode('utf-8', errors='replace')
            print(f"  ← HTTP {e.code} ERROR: {body_preview}", flush=True)
            self.send_response(e.code)
            for key, val in e.headers.items():
                if key.lower() not in ['transfer-encoding', 'content-encoding', 'access-control-allow-origin']:
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(res_data)
        except Exception as e:
            print(f"  ← PROXY EXCEPTION: {e}", flush=True)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

if __name__ == '__main__':
    print(f"Starting CORS Proxy Web Server on port {PORT}...")
    print(f"Access the dashboard at http://localhost:{PORT}")
    server = http.server.HTTPServer(('127.0.0.1', PORT), ProxyHTTPRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        server.server_close()
