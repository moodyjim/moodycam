# -*- coding: utf-8 -*-
"""A small WebSocket client using only the Python standard library.

Why this exists: CoreELEC can't pip-install packages, and this keeps the
add-on free of dependencies. It only does what MoodyCam needs: connect over
TLS, read text messages, answer pings, send pings, and close.
"""
import base64
import hashlib
import os
import socket
import struct
import threading
import time

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WSClosed(Exception):
    """The connection ended (server closed it, or it broke)."""


class WSIdle(Exception):
    """Nothing arrived for one read timeout. Not an error by itself."""


class WSHandshakeError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status


class WebSocket(object):
    def __init__(self, host, port, path, headers, ssl_ctx, read_timeout=30):
        self.host = host
        self.port = port
        self.path = path
        self.headers = headers or {}
        self.ssl_ctx = ssl_ctx
        self.read_timeout = read_timeout
        self.sock = None
        self._buf = b""
        self._send_lock = threading.Lock()
        self.last_rx = time.time()

    # ---- connection -------------------------------------------------------
    def connect(self):
        raw = socket.create_connection((self.host, self.port), timeout=10)
        if self.ssl_ctx is not None:
            self.sock = self.ssl_ctx.wrap_socket(raw, server_hostname=self.host)
        else:
            self.sock = raw
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        lines = [
            "GET %s HTTP/1.1" % self.path,
            "Host: %s" % self.host,
            "Upgrade: websocket",
            "Connection: Upgrade",
            "Sec-WebSocket-Key: %s" % key,
            "Sec-WebSocket-Version: 13",
        ]
        for name, value in self.headers.items():
            lines.append("%s: %s" % (name, value))
        self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("utf-8"))

        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WSClosed("server closed during handshake")
            response += chunk
            if len(response) > 65536:
                raise WSHandshakeError(0, "handshake response too large")
        head, self._buf = response.split(b"\r\n\r\n", 1)
        head_lines = head.decode("iso-8859-1").split("\r\n")
        parts = head_lines[0].split(" ", 2)
        status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        if status != 101:
            raise WSHandshakeError(status, "handshake failed: %s" % head_lines[0])
        expected = base64.b64encode(
            hashlib.sha1((key + _GUID).encode("ascii")).digest()).decode("ascii")
        accept = ""
        for line in head_lines[1:]:
            if line.lower().startswith("sec-websocket-accept:"):
                accept = line.split(":", 1)[1].strip()
        if accept != expected:
            raise WSHandshakeError(status, "bad Sec-WebSocket-Accept from server")
        self.sock.settimeout(self.read_timeout)
        self.last_rx = time.time()

    def close(self):
        sock, self.sock = self.sock, None
        if sock is None:
            return
        try:
            self._send_frame(0x8, struct.pack("!H", 1000), sock=sock)
        except Exception:
            pass
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass

    # ---- sending ----------------------------------------------------------
    def ping(self):
        self._send_frame(0x9, b"")

    def _send_frame(self, opcode, payload, sock=None):
        sock = sock or self.sock
        if sock is None:
            raise WSClosed("not connected")
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", length)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self._send_lock:
            sock.sendall(bytes(header) + masked)

    # ---- receiving --------------------------------------------------------
    def _recv_exact(self, n, idle_ok=False):
        timeouts = 0
        while len(self._buf) < n:
            sock = self.sock
            if sock is None:
                raise WSClosed("closed")
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                if idle_ok and not self._buf:
                    raise WSIdle()
                timeouts += 1
                if timeouts >= 3:
                    raise WSClosed("stalled in the middle of a message")
                continue
            except OSError as e:
                raise WSClosed(str(e))
            if not chunk:
                raise WSClosed("server closed the connection")
            self.last_rx = time.time()
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def recv_message(self):
        """Return the next text (str) or binary (bytes) message.

        Raises WSIdle if nothing arrived for read_timeout seconds.
        """
        fragments = []
        msg_opcode = None
        while True:
            b1, b2 = bytearray(self._recv_exact(2, idle_ok=not fragments))
            fin = b1 & 0x80
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else None
            payload = self._recv_exact(length) if length else b""
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

            if opcode == 0x9:          # ping -> pong
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:          # pong (keeps last_rx fresh)
                continue
            if opcode == 0x8:          # close
                raise WSClosed("server sent close")
            if opcode in (0x1, 0x2):
                msg_opcode = opcode
                fragments = [payload]
            elif opcode == 0x0:
                fragments.append(payload)
            if fin and msg_opcode is not None:
                data = b"".join(fragments)
                if msg_opcode == 0x1:
                    return data.decode("utf-8", "replace")
                return data
