"""A local stand-in for the Hugging Face model repository, used by the downloader tests and the GUI checks."""
import hashlib
import http.server
import json
import os
import socketserver
import threading

MIB = 1024 * 1024
CONTENT = {
    "config.json": b'{"k": 1}',
    "preprocessor_config.json": b"{}",
    "tokenizer.json": b"t" * 5000,
    "vocabulary.json": b"v" * 3000,
    "model.bin": os.urandom(3 * MIB + 123),
}


class Hub:
    """A fake model repository: the API listing plus resolvable files with Range support."""

    def __init__(self):
        self.files = dict(CONTENT)
        self.requests = []          # (path, Range header)
        self.ignore_range = False
        self.fail_api_with = None
        self.omit = set()
        self.server = None

    def listing(self):
        entries = []
        for name, data in self.files.items():
            if name in self.omit:
                continue
            entry = {"type": "file", "path": name, "size": len(data)}
            if name == "model.bin":
                entry["lfs"] = {"oid": hashlib.sha256(CONTENT[name]).hexdigest(), "size": len(data)}
            entries.append(entry)
        return json.dumps(entries).encode()


def start_hub():
    """Starts the fake repository; returns (state, stop function)."""
    state = Hub()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            state.requests.append((self.path, self.headers.get("Range")))
            if self.path.startswith("/api/"):
                if state.fail_api_with:
                    return self.send_error(state.fail_api_with)
                return self._send(200, state.listing())
            data = state.files.get(self.path.rsplit("/", 1)[-1])
            if data is None:
                return self.send_error(404)
            range_header = self.headers.get("Range")
            if range_header and not state.ignore_range:
                start = int(range_header.split("=")[1].rstrip("-"))
                return self._send(206, data[start:])
            return self._send(200, data)

        def _send(self, status, body):
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state.url = f"http://127.0.0.1:{server.server_address[1]}"

    def stop():
        server.shutdown()
        server.server_close()
    return state, stop
