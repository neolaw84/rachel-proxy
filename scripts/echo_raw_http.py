"""Low-level raw TCP/HTTP echo server for debugging incoming client requests.

Captures the exact raw bytes received on the wire (request line, headers, and body)
before any HTTP framework or JSON parser touches them, prints them to stdout,
saves the latest request to ``docs/debug-raw-http-request.txt``, and responds
with a permissive CORS 200 OK so browser clients (e.g. JanitorAI) complete
preflight and POST requests cleanly.

Usage:
    venv/Scripts/python.exe scripts/echo_raw_http.py --port 8000
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import socket
import threading

OUTPUT_FILE: Path = (
    Path(__file__).resolve().parent.parent / "docs" / "debug-raw-http-request.txt"
)


def _recv_http_request(conn: socket.socket, idle_timeout: float = 0.5) -> bytes:
    """Read raw HTTP request bytes from a TCP socket without framework parsing."""
    conn.settimeout(5.0)
    chunks: list[bytes] = []
    header_end = -1
    content_length: int | None = None

    while True:
        try:
            data = conn.recv(65536)
        except socket.timeout:
            break
        if not data:
            break
        chunks.append(data)
        buf = b"".join(chunks)

        if header_end == -1:
            idx = buf.find(b"\r\n\r\n")
            if idx != -1:
                header_end = idx + 4
                header_text = buf[:idx].decode("iso-8859-1", errors="replace")
                for line in header_text.split("\r\n")[1:]:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        if k.strip().lower() == "content-length":
                            try:
                                content_length = int(v.strip())
                            except ValueError:
                                pass
                # Once headers are complete, use a short idle timeout if no Content-Length
                conn.settimeout(idle_timeout)

        if header_end != -1:
            body_len = len(buf) - header_end
            if content_length is not None and body_len >= content_length:
                break
            if content_length is None and b"transfer-encoding: chunked" not in buf[:header_end].lower():
                break

    return b"".join(chunks)


def _handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    try:
        raw = _recv_http_request(conn)
        timestamp = datetime.now(timezone.utc).isoformat()
        text = raw.decode("utf-8", errors="replace")
        banner = f"=== {timestamp} from {addr[0]}:{addr[1]} ({len(raw)} bytes) ===\n"
        report = banner + text + "\n"

        print(report, flush=True)
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(report, encoding="utf-8")

        resp_body = b'{"echo":"ok","bytes_received":' + str(len(raw)).encode("ascii") + b"}"
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Access-Control-Allow-Origin: *\r\n"
            b"Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS\r\n"
            b"Access-Control-Allow-Headers: *\r\n"
            + f"Content-Length: {len(resp_body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + resp_body
        )
        conn.sendall(response)
    except Exception as exc:
        print(f"[echo_raw_http] Error handling {addr}: {exc}", flush=True)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Low-level raw HTTP request echo server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    args = parser.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(16)
    print(f"Raw HTTP echo server listening on http://{args.host}:{args.port}")
    print(f"Writing latest raw request to: {OUTPUT_FILE}")

    try:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=_handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\nShutting down raw HTTP echo server.")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
