"""Container liveness only. No file contents or file operations over HTTP."""
from http.server import BaseHTTPRequestHandler, HTTPServer


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = b'{"status":"ok","application":"lab1-console"}\n'
        self.send_response(200 if self.path == '/health' else 404)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload) if self.path == '/health' else 0))
        self.end_headers()
        if self.path == '/health':
            self.wfile.write(payload)


if __name__ == '__main__':
    # Binds inside an isolated container. Host publication is loopback-only.
    HTTPServer(('0.0.0.0', 8080), HealthHandler).serve_forever()  # nosec B104
