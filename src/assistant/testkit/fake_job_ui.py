"""A stand-in for the job project's job_ui.py: serves 200 on /tracker (HTML, no JSON ping, no quit
call), takes --port and --no-browser like the real one. Run as a script by the tests."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        code, body = (200, b"<html>Tracker</html>") if self.path.split("?")[0] == "/tracker" else (404, b"no")
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--no-browser", action="store_true")
    ThreadingHTTPServer(("127.0.0.1", parser.parse_args().port), Handler).serve_forever()
