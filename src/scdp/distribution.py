"""Authenticated immutable package delivery on a loopback listener."""
import argparse
import hmac
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def server(root, token_file, host="127.0.0.1", port=5129):
    if host != "127.0.0.1":
        raise ValueError("distribution_requires_loopback")
    root, token_file = Path(root).resolve(), Path(token_file)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Access receipts are maintained by deployment logging; never log headers.

        def do_HEAD(self):
            self.deliver(head=True)

        def do_GET(self):
            self.deliver(head=False)

        def deliver(self, head):
            try:
                token = next(line.strip().removeprefix("Bearer ") for line in token_file.read_text().splitlines()
                             if line.strip() and not line.lstrip().startswith("#"))
            except (OSError, StopIteration, UnicodeError):
                self.send_error(503)
                return
            if not hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer "+token).encode()):
                self.send_error(401)
                return
            parsed = urlsplit(self.path)
            if parsed.query or parsed.fragment:
                self.send_error(404)
                return
            name = parsed.path.removeprefix("/")
            if name not in ("latest.json", "previous.json") and not re.fullmatch(r"[0-9a-f]{64}\.tar\.gz", name):
                self.send_error(404)
                return
            target = root/name
            if target.is_symlink() or not target.is_file():
                self.send_error(404)
                return
            try:
                with target.open("rb") as stream:
                    size = os.fstat(stream.fileno()).st_size
                    start, end = 0, size-1
                    ranged = self.headers.get("Range")
                    if ranged:
                        match = re.fullmatch(r"bytes=(\d+)-(\d*)", ranged)
                        if not match:
                            self.send_error(416)
                            return
                        start = int(match[1])
                        end = min(size-1, int(match[2])) if match[2] else size-1
                        if start > end or start >= size:
                            self.send_error(416)
                            return
                    self.send_response(206 if ranged else 200)
                    self.send_header("Content-Type", "application/gzip" if name.endswith(".gz") else "application/json")
                    self.send_header("Content-Length", str(end-start+1))
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Cache-Control", "private, max-age=31536000, immutable" if name.endswith(".gz") else "no-cache")
                    if ranged:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.end_headers()
                    if not head:
                        stream.seek(start)
                        remaining = end-start+1
                        while remaining:
                            data = stream.read(min(65536, remaining))
                            if not data:
                                raise OSError("package_short_read")
                            self.wfile.write(data)
                            remaining -= len(data)
            except (BrokenPipeError, ConnectionResetError):
                return

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--port", type=int, default=5129)
    args = parser.parse_args()
    with server(args.root, args.token_file, port=args.port) as http:
        http.serve_forever()


if __name__ == "__main__":
    main()
