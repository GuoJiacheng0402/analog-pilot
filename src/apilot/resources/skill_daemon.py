#!/usr/bin/env python3
"""AnalogPilot SKILL daemon (runs on the remote host as a Virtuoso IPC child)."""
import os
import select
import socket
import sys
import time

ETX = b"\x03"
SOH = b"\x01"
STX = b"\x02"

TRACE = os.environ.get("APILOT_DAEMON_TRACE", "")  # set to a path to enable tracing


def trace(msg):
    if not TRACE:
        return
    try:
        with open(TRACE, "a") as f:
            f.write("%.3f %s\n" % (time.time(), msg))
    except Exception:
        pass


def _stdin_fd():
    return sys.stdin.fileno()


def _stdout():
    return getattr(sys.stdout, "buffer", sys.stdout)


def _write_skill(skill_bytes):
    out = _stdout()
    out.write(skill_bytes)
    out.flush()


def eval_skill(expr_bytes, reply_timeout=30.0):
    """Send one SKILL expression to Virtuoso and return (status, payload)."""
    skill = expr_bytes.decode("utf-8", "replace").strip()
    # Wrap so we capture the value, flush Virtuoso's IPC pipe (hiFlush), and
    # return the value. Trailing newline is REQUIRED: Virtuoso's IPC data
    # handler is line-triggered.
    send = ("let((__ap_r) __ap_r=%s hiFlush() __ap_r)\n" % skill).encode("utf-8")
    trace("WRITE %r" % send)
    _write_skill(send)
    fd = _stdin_fd()
    buf = b""
    deadline = time.time() + reply_timeout
    while ETX not in buf:
        remaining = deadline - time.time()
        if remaining <= 0:
            trace("REPLY TIMEOUT buf=%r" % buf)
            return "ERR", b"timeout waiting for Virtuoso reply"
        r, _, _ = select.select([fd], [], [], remaining)
        if not r:
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            trace("STDIN EOF buf=%r" % buf)
            return "ERR", b"daemon lost stdin from Virtuoso"
        buf += chunk
    trace("REPLY %r" % buf)
    frame = buf.split(SOH, 1)[-1].rstrip(ETX)
    status, _, payload = frame.partition(STX)
    return status.decode("utf-8", "replace").strip(), payload


def recv_request(conn):
    header = b""
    while b"\n" not in header:
        ch = conn.recv(1)
        if not ch:
            return None
        header += ch
    line = header.rstrip(b"\n")
    if line[:1] == b"C":
        line = line[1:]
    try:
        length = int(line)
    except ValueError:
        return None
    data = b""
    while len(data) < length:
        chunk = conn.recv(length - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def send_reply(conn, status_char, payload_bytes):
    header = ("%s%08d\n" % (status_char, len(payload_bytes))).encode("ascii")
    conn.sendall(header + payload_bytes)


def serve(host, port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(8)
    trace("LISTEN %s:%d pid=%d" % (host, port, os.getpid()))
    while True:
        conn, addr = srv.accept()
        try:
            while True:
                cmd = recv_request(conn)
                if cmd is None:
                    break
                trace("RECV %r" % cmd)
                status, payload = eval_skill(cmd)
                send_reply(conn, "S" if status == "OK" else "E", payload)
        except Exception as exc:
            trace("CLIENT ERR %r" % exc)
        finally:
            conn.close()


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    try:
        serve(host, port)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
